"""
Post-Scan Health Check — runs after every scan cycle.

Checks all known failure modes identified in the system audit (2026-03-02):
  C1  — duplicate open positions (should be 0 after unique index added)
  C2  — override endpoints auth (warns if OVERRIDE_API_KEY not set)
  H1  — bar fetch coverage (verifies BREAKOUT_FETCH_DAYS >= 550)
  H2  — Claude gate circuit breaker state
  H3  — equity curve baseline accuracy
  H4  — delisted tickers in watchlist
  M1  — catalyst cache efficiency
  M2  — unvalidated symbols in watchlist
  M3  — stale pending proposals (alpha scanner)
  M4  — chat log file size
  M5  — SSE subscriber count
  M6  — active watcher thread count
  GEN — overall scan coverage (symbols scanned vs total watchlist)
"""
import logging
import os
import time
import threading
from datetime import datetime, timezone
from typing import Any

from app.database import SessionLocal
from app.config import get_settings

logger = logging.getLogger(__name__)

# Tickers known to be delisted/non-tradeable — presence in watchlist is a bug
_DELISTED = {"GOEV", "NKLA", "SOLO", "RIDE", "ASTR", "FSR", "SPCE"}

# Status constants
OK      = "OK"
WARN    = "WARN"
FAIL    = "FAIL"
INFO    = "INFO"


def _check(name: str, status: str, detail: str) -> dict:
    return {"check": name, "status": status, "detail": detail, "ts": datetime.now(timezone.utc).isoformat()}


def run(scan_stats: dict | None = None) -> list[dict]:
    """
    Run all health checks. `scan_stats` is the optional dict returned by
    scan_all() or run_scan_cycle(), used to enrich some checks.

    Returns list of check result dicts, each: {check, status, detail, ts}
    """
    results = []
    db = SessionLocal()
    try:
        s = get_settings()

        # ── C1: Duplicate open positions ────────────────────────────────────
        try:
            from app.models.position import Position, PositionStatus
            from sqlalchemy import func
            dupes = (
                db.query(Position.symbol, func.count(Position.id).label("cnt"))
                .filter(Position.status == PositionStatus.OPEN)
                .group_by(Position.symbol)
                .having(func.count(Position.id) > 1)
                .all()
            )
            if dupes:
                results.append(_check("C1_duplicate_positions", FAIL,
                    f"DUPLICATE OPEN POSITIONS DETECTED: {[(d.symbol, d.cnt) for d in dupes]} — "
                    f"manual review required"))
            else:
                results.append(_check("C1_duplicate_positions", OK,
                    "No duplicate open positions found"))
        except Exception as e:
            results.append(_check("C1_duplicate_positions", WARN, f"Check failed: {e}"))

        # ── C2: Override endpoint auth ───────────────────────────────────────
        if s.override_api_key:
            results.append(_check("C2_override_auth", OK,
                "OVERRIDE_API_KEY is set — override endpoints are protected"))
        else:
            results.append(_check("C2_override_auth", WARN,
                "OVERRIDE_API_KEY not set — override/pipeline endpoints are unauthenticated (OK for dev)"))

        # ── H1: Bar fetch coverage ───────────────────────────────────────────
        try:
            from app.services.breakout_scanner import _BREAKOUT_FETCH_DAYS
            if _BREAKOUT_FETCH_DAYS >= 550:
                results.append(_check("H1_bar_fetch_days", OK,
                    f"_BREAKOUT_FETCH_DAYS={_BREAKOUT_FETCH_DAYS} (≥550 required)"))
            else:
                results.append(_check("H1_bar_fetch_days", FAIL,
                    f"_BREAKOUT_FETCH_DAYS={_BREAKOUT_FETCH_DAYS} — increase to ≥550 to avoid silent scan failures"))
        except Exception as e:
            results.append(_check("H1_bar_fetch_days", WARN, f"Check failed: {e}"))

        # ── H2: Claude gate circuit breaker ─────────────────────────────────
        try:
            from app.services import claude_gate
            cb_open = time.time() < claude_gate._cb_open_until
            failures = claude_gate._cb_failures
            if cb_open:
                results.append(_check("H2_claude_circuit", FAIL,
                    f"Claude gate circuit breaker OPEN (failures={failures}) — trades are being REJECTED"))
            elif failures > 0:
                results.append(_check("H2_claude_circuit", WARN,
                    f"Claude gate has {failures} recent failure(s) — circuit threshold is {claude_gate._CB_THRESHOLD}"))
            else:
                results.append(_check("H2_claude_circuit", OK,
                    f"Claude gate healthy (failures=0, circuit closed)"))
        except Exception as e:
            results.append(_check("H2_claude_circuit", WARN, f"Check failed: {e}"))

        # ── H3: Equity curve baseline ────────────────────────────────────────
        # Now uses dynamic starting capital from Alpaca — just verify API connectivity
        try:
            from app.integrations.alpaca_client import AlpacaClient
            acct = AlpacaClient().get_account()
            pv = acct.get("portfolio_value") if acct else None
            if pv:
                results.append(_check("H3_equity_baseline", OK,
                    f"Alpaca account reachable — portfolio_value=${float(pv):,.0f} "
                    f"(dynamic baseline, no hardcoded mismatch)"))
            else:
                results.append(_check("H3_equity_baseline", WARN,
                    "Alpaca account returned no portfolio_value"))
        except Exception as e:
            results.append(_check("H3_equity_baseline", WARN, f"Alpaca account check failed: {e}"))

        # ── H4: Delisted tickers in watchlist ────────────────────────────────
        try:
            from app.models.watchlist import WatchlistItem
            active_symbols = {
                row[0] for row in db.query(WatchlistItem.symbol)
                .filter(WatchlistItem.active == True).all()
            }
            found_delisted = active_symbols & _DELISTED
            if found_delisted:
                results.append(_check("H4_delisted_tickers", WARN,
                    f"Delisted/zombie tickers still in active watchlist: {sorted(found_delisted)} — "
                    f"run watchlist cleanup or deactivate manually"))
            else:
                results.append(_check("H4_delisted_tickers", OK,
                    "No known delisted tickers in active watchlist"))
        except Exception as e:
            results.append(_check("H4_delisted_tickers", WARN, f"Check failed: {e}"))

        # ── M1: Catalyst cache note (informational) ──────────────────────────
        results.append(_check("M1_catalyst_cache", INFO,
            "Catalyst checks fire per-breakout with no cache — acceptable for low-volume scans. "
            "Monitor Finnhub rate limit errors if >10 breakouts per scan."))

        # ── M2: Unvalidated symbols ──────────────────────────────────────────
        # Check if any symbols in watchlist look suspicious (numbers, >5 chars, etc.)
        try:
            from app.models.watchlist import WatchlistItem
            all_syms = [row[0] for row in db.query(WatchlistItem.symbol)
                        .filter(WatchlistItem.active == True).all()]
            suspicious = [s for s in all_syms if not s.replace("-", "").isalpha() or len(s) > 5]
            if suspicious:
                results.append(_check("M2_symbol_validation", WARN,
                    f"Suspicious symbols in watchlist (non-alpha or >5 chars): {suspicious[:10]}"))
            else:
                results.append(_check("M2_symbol_validation", OK,
                    f"All {len(all_syms)} active symbols look well-formed"))
        except Exception as e:
            results.append(_check("M2_symbol_validation", WARN, f"Check failed: {e}"))

        # ── M3: Stale pending proposals ──────────────────────────────────────
        try:
            from app.services.alpha_scanner import _pending_proposals
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            stale = [k for k, v in _pending_proposals.items()
                     if v.get("created_at", cutoff) < cutoff]
            total = len(_pending_proposals)
            if stale:
                results.append(_check("M3_pending_proposals", WARN,
                    f"{len(stale)} of {total} pending alpha proposals are >24h old (memory leak) — "
                    f"they will be pruned on next user reply"))
            else:
                results.append(_check("M3_pending_proposals", OK,
                    f"{total} pending proposal(s) — none stale"))
        except Exception as e:
            results.append(_check("M3_pending_proposals", WARN, f"Check failed: {e}"))

        # ── M4: Chat log file size ───────────────────────────────────────────
        try:
            log_path = os.path.join(
                os.path.dirname(__file__), "../../logs/chat/messages.jsonl"
            )
            log_path = os.path.normpath(log_path)
            if os.path.exists(log_path):
                size_mb = os.path.getsize(log_path) / (1024 * 1024)
                if size_mb > 10:
                    results.append(_check("M4_chat_log_size", WARN,
                        f"Chat log is {size_mb:.1f}MB — consider rotation (safe threshold: 10MB)"))
                else:
                    results.append(_check("M4_chat_log_size", OK,
                        f"Chat log size: {size_mb:.2f}MB"))
            else:
                results.append(_check("M4_chat_log_size", OK, "Chat log not yet created"))
        except Exception as e:
            results.append(_check("M4_chat_log_size", WARN, f"Check failed: {e}"))

        # ── M5: SSE subscriber count ─────────────────────────────────────────
        try:
            from app.services.agent_tracker import _subscribers
            count = len(_subscribers)
            if count > 20:
                results.append(_check("M5_sse_subscribers", WARN,
                    f"{count} SSE subscribers — unusually high, possible stale connections"))
            else:
                results.append(_check("M5_sse_subscribers", OK,
                    f"{count} active SSE subscriber(s)"))
        except Exception as e:
            results.append(_check("M5_sse_subscribers", WARN, f"Check failed: {e}"))

        # ── M6: Watcher thread count ─────────────────────────────────────────
        try:
            from app.services.trade_executor import _WATCHER_SEM
            active_watchers = 10 - _WATCHER_SEM._value  # semaphore value = remaining slots
            if active_watchers >= 8:
                results.append(_check("M6_watcher_threads", WARN,
                    f"{active_watchers}/10 watcher threads active — approaching semaphore cap"))
            else:
                results.append(_check("M6_watcher_threads", OK,
                    f"{active_watchers}/10 watcher threads active"))
        except Exception as e:
            results.append(_check("M6_watcher_threads", WARN, f"Check failed: {e}"))

        # ── SCAN COVERAGE: Symbols scanned vs total watchlist ────────────────
        try:
            from app.models.watchlist import WatchlistItem
            total_active  = db.query(WatchlistItem).filter(
                WatchlistItem.active == True,
                WatchlistItem.structure_clean == True
            ).count()
            scanned = scan_stats.get("symbols_scanned", 0) if scan_stats else None
            if scanned is not None:
                coverage = (scanned / total_active * 100) if total_active else 100
                status = OK if coverage >= 80 else WARN
                results.append(_check("GEN_scan_coverage", status,
                    f"Scanned {scanned}/{total_active} clean symbols ({coverage:.0f}% coverage)"))
            else:
                results.append(_check("GEN_scan_coverage", INFO,
                    f"Coverage unknown (no scan_stats provided) — {total_active} clean symbols in watchlist"))
        except Exception as e:
            results.append(_check("GEN_scan_coverage", WARN, f"Check failed: {e}"))

        # ── OVERALL SYSTEM HEALTH ────────────────────────────────────────────
        fails = [r for r in results if r["status"] == FAIL]
        warns = [r for r in results if r["status"] == WARN]
        overall = FAIL if fails else (WARN if warns else OK)
        summary = (
            f"Health: {overall} — "
            f"{len(fails)} FAIL / {len(warns)} WARN / "
            f"{len([r for r in results if r['status']==OK])} OK"
        )
        results.append(_check("OVERALL", overall, summary))

        # Log the summary
        log_fn = logger.error if fails else (logger.warning if warns else logger.info)
        log_fn(f"[HealthCheck] {summary}")
        for r in results:
            if r["status"] in (FAIL, WARN):
                logger.warning(f"[HealthCheck] {r['check']}: {r['detail']}")

        # Broadcast to dashboard SSE
        try:
            from app.services.agent_tracker import broadcast
            broadcast("health_check", {
                "overall": overall,
                "fails": len(fails),
                "warns": len(warns),
                "results": results,
            })
        except Exception:
            pass  # SSE broadcast is best-effort

    finally:
        db.close()

    return results
