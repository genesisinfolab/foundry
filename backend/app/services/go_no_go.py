"""
Go / No-Go — pre-flight gate before flipping to live money.

Evaluates two categories of criteria against live paper-trading data:

  PERFORMANCE  — thresholds the paper account must meet (sample size,
                 win rate, W/L ratio, drawdown, profit factor, age).

  SYSTEM       — health checks that must pass regardless of returns
                 (Alpaca connection, scanner activity, kill switch state,
                 paper-mode confirmation).

Call evaluate(db) → GoNoGoReport at any time; wire it to
GET /api/go-no-go so the dashboard can show a green/red checklist.

The thresholds are defined once here and never changed at runtime.
That makes them a pre-commitment — the point is to decide the bar
BEFORE looking at results, not to adjust it until the strategy "passes".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy.orm import Session

from app.models.position import Position, PositionStatus
from app.models.alert import Alert

logger = logging.getLogger(__name__)


# ── Thresholds (change these before live flip, never during) ─────────────────
#
# PHASE 1 — 4-day wide gate (hourly / daily / weekly bars)
#
# 4 calendar days yields at most ~26 hourly signals, ~4 daily signals,
# and <1 full weekly bar.  Sample size is tiny, so:
#   • min_trades is set very low (3) — just enough to have any signal at all.
#   • win_rate threshold is 40 %.  Math: at W/L = 1.5 the break-even win rate
#     is exactly 40 % (0.4×1.5 − 0.6×1.0 = 0).  We gate above that via
#     profit_factor ≥ 1.1, which is the binding filter at this phase.
#   • max_drawdown is wide (35 %) because a single bad trade in 3 can look
#     catastrophic on paper before the law of large numbers kicks in.
#
# Tighten all thresholds once you have ≥ 20 trades / 30 days of history.

_THRESHOLDS = {
    # Performance
    "min_trades":     3,       # minimum closed paper trades
    "paper_days":     4,       # minimum calendar days since first paper trade
    "win_rate":       40.0,    # % — break-even floor for W/L ≥ 1.5
    "wl_ratio":        1.5,    # avg_win / abs(avg_loss)  (wide start)
    "profit_factor":   1.1,    # gross_wins / gross_losses — the binding gate
    "max_drawdown":   35.0,    # % — wider tolerance for 3–5 trade sample
    # System
    "scanner_max_age": 25,     # hours — scanner must have run within this window
}


@dataclass
class Criterion:
    id:        str
    label:     str
    category:  str           # "performance" | "system"
    threshold: str           # human-readable required value
    actual:    str           # human-readable measured value
    passed:    bool
    blocker:   bool = True   # if False, this is advisory-only (won't block go)
    note:      str = ""


@dataclass
class GoNoGoReport:
    verdict:    str                      # "go" | "no_go"
    blockers:   list[str]                # labels of failing blocker criteria
    criteria:   list[Criterion] = field(default_factory=list)
    evaluated_at: str = ""


def evaluate(db: Session) -> GoNoGoReport:
    """
    Evaluate all go/no-go criteria.
    Returns a GoNoGoReport with per-criterion pass/fail and an overall verdict.
    """
    criteria: list[Criterion] = []

    # ── Gather closed paper trades ────────────────────────────────────────────
    closed = db.query(Position).filter(
        Position.status.in_([PositionStatus.CLOSED, PositionStatus.STOPPED_OUT])
    ).order_by(Position.opened_at).all()

    pnl_pcts: list[float] = []
    for p in closed:
        if p.cost_basis and p.cost_basis > 0:
            pnl_pcts.append(float(p.realized_pnl or 0) / float(p.cost_basis) * 100)

    wins   = [x for x in pnl_pcts if x > 0]
    losses = [x for x in pnl_pcts if x <= 0]
    total  = len(pnl_pcts)

    win_rate      = (len(wins) / total * 100) if total else 0.0
    avg_win       = float(np.mean(wins))   if wins   else 0.0
    avg_loss      = float(np.mean(losses)) if losses else 0.0   # negative number
    gross_wins    = sum(wins)
    gross_losses  = abs(sum(losses)) or 1.0
    profit_factor = gross_wins / gross_losses

    wl_ratio = avg_win / abs(avg_loss) if avg_loss < 0 else 0.0

    # Sequential equity curve for drawdown
    equity = 100_000.0
    peak   = equity
    max_dd = 0.0
    for p in sorted(closed, key=lambda x: x.closed_at or datetime.min.replace(tzinfo=timezone.utc)):
        if p.cost_basis and p.cost_basis > 0:
            pct = float(p.realized_pnl or 0) / float(p.cost_basis)
            equity += equity * 0.05 * pct * 100 / 100
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Paper trading age (days since first trade)
    first_trade = closed[0].opened_at if closed else None
    paper_days = (
        (datetime.now(timezone.utc) - first_trade).days
        if first_trade and first_trade.tzinfo
        else (
            (datetime.now(timezone.utc) - first_trade.replace(tzinfo=timezone.utc)).days
            if first_trade else 0
        )
    )

    t = _THRESHOLDS

    # ── Performance criteria ──────────────────────────────────────────────────

    criteria.append(Criterion(
        id="min_trades",
        label="Paper trades completed",
        category="performance",
        threshold=f"≥ {t['min_trades']}",
        actual=str(total),
        passed=total >= t["min_trades"],
    ))

    criteria.append(Criterion(
        id="paper_days",
        label="Paper trading history",
        category="performance",
        threshold=f"≥ {t['paper_days']} days",
        actual=f"{paper_days} days",
        passed=paper_days >= t["paper_days"],
    ))

    criteria.append(Criterion(
        id="win_rate",
        label="Win rate",
        category="performance",
        threshold=f"≥ {t['win_rate']:.0f}%",
        actual=f"{win_rate:.1f}%",
        passed=win_rate >= t["win_rate"],
    ))

    criteria.append(Criterion(
        id="wl_ratio",
        label="Avg win / avg loss",
        category="performance",
        threshold=f"≥ {t['wl_ratio']:.1f}×",
        actual=f"{wl_ratio:.2f}×" if losses else "n/a",
        passed=wl_ratio >= t["wl_ratio"],
    ))

    criteria.append(Criterion(
        id="profit_factor",
        label="Profit factor",
        category="performance",
        threshold=f"≥ {t['profit_factor']:.1f}",
        actual=f"{profit_factor:.2f}",
        passed=profit_factor >= t["profit_factor"],
    ))

    criteria.append(Criterion(
        id="max_drawdown",
        label="Max drawdown",
        category="performance",
        threshold=f"≤ {t['max_drawdown']:.0f}%",
        actual=f"{max_dd:.1f}%",
        passed=max_dd <= t["max_drawdown"],
        note="Lower is better",
    ))

    # ── System health criteria ────────────────────────────────────────────────

    # Alpaca connectivity
    alpaca_ok = False
    alpaca_note = ""
    try:
        from app.integrations.alpaca_client import AlpacaClient
        acct = AlpacaClient().get_account()
        alpaca_ok = bool(acct.get("portfolio_value") is not None)
        alpaca_note = f"${acct.get('portfolio_value', 0):,.0f} portfolio" if alpaca_ok else "no portfolio_value"
    except Exception as e:
        alpaca_note = str(e)[:60]

    criteria.append(Criterion(
        id="alpaca_connected",
        label="Alpaca API connection",
        category="system",
        threshold="Connected",
        actual="OK" if alpaca_ok else f"FAIL: {alpaca_note}",
        passed=alpaca_ok,
        note=alpaca_note,
    ))

    # Paper mode confirmed
    from app.config import get_settings
    s = get_settings()
    criteria.append(Criterion(
        id="paper_mode",
        label="Running in paper mode",
        category="system",
        threshold="True",
        actual=str(s.alpaca_paper),
        passed=s.alpaca_paper,
        note="Must be True before live flip; manually set to False to go live",
    ))

    # Kill switch not paused
    from app.services import kill_switch
    ks = kill_switch.status()
    criteria.append(Criterion(
        id="engine_active",
        label="Engine not paused",
        category="system",
        threshold="Not paused",
        actual="PAUSED" if ks["paused"] else "Active",
        passed=not ks["paused"],
        note=ks.get("reason", "") if ks["paused"] else "",
    ))

    # Breakout scanner ran recently (check alerts table for a breakout alert within 25h,
    # OR simply check that at least one reasoning entry was written today)
    scanner_ok = False
    scanner_note = "No scan in last 25h"
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=t["scanner_max_age"])
        recent_scan_alert = db.query(Alert).filter(
            Alert.alert_type == "breakout",
            Alert.created_at >= cutoff,
        ).first()
        if recent_scan_alert:
            scanner_ok   = True
            scanner_note = f"Last breakout alert: {recent_scan_alert.created_at.strftime('%Y-%m-%d %H:%M')}"
        else:
            # Also accept if any alert (even "no breakouts") was created recently —
            # the scheduler ran but found nothing.  Check reasoning JSONL.
            try:
                from app.services.reasoning_log import recent as recent_reasoning
                entries = recent_reasoning(5)
                recent_agent_entry = next(
                    (e for e in entries
                     if e.get("agent") == "breakout_scanner"),
                    None,
                )
                if recent_agent_entry:
                    ts = recent_agent_entry.get("ts", "")
                    if ts:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if dt >= cutoff:
                            scanner_ok   = True
                            scanner_note = f"Last scan: {dt.strftime('%Y-%m-%d %H:%M')}"
            except Exception:
                pass
    except Exception as e:
        scanner_note = str(e)[:60]

    criteria.append(Criterion(
        id="scanner_active",
        label=f"Breakout scanner ran < {t['scanner_max_age']}h ago",
        category="system",
        threshold=f"< {t['scanner_max_age']}h",
        actual="OK" if scanner_ok else scanner_note,
        passed=scanner_ok,
        blocker=False,   # advisory: scanner may not run on weekends
        note="Advisory only — scanner won't run outside market hours",
    ))

    # ── Verdict ───────────────────────────────────────────────────────────────
    blockers = [c.label for c in criteria if c.blocker and not c.passed]
    verdict  = "go" if not blockers else "no_go"

    return GoNoGoReport(
        verdict=verdict,
        blockers=blockers,
        criteria=criteria,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )
