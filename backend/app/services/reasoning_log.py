"""
Reasoning Log

Writes a JSONL record to logs/reasoning/YYYY-MM-DD.jsonl for every
significant decision the system makes — entry, skip, pyramid, exit.

Complements the pre-trade audit_log.py:
  audit_log     → records the ORDER (what was placed, price, qty)
  reasoning_log → records the DECISION (why: corners, conviction, notes)

Also fans the record out to the live dashboard via agent_tracker.
Never raises: a log failure must never block a trade.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_LOG_DIR = Path(__file__).resolve().parents[3] / "logs" / "reasoning"


def write_reasoning(
    agent: str,
    event: str,
    symbol: str,
    action: str,
    *,
    corners: Optional[dict] = None,
    conviction: Optional[int] = None,
    notes: str = "",
    extra: Optional[dict] = None,
) -> None:
    """
    Write one reasoning record and broadcast it to the dashboard.

    Args:
        agent:      Service name  (trade_executor | risk_manager | breakout_scanner)
        event:      Decision type (shotgun_entry | pyramid | stop_loss | profit_take | skip)
        symbol:     Ticker symbol
        action:     What was decided (entry | hold | exit | skip | watch)
        corners:    Dict of corner evaluations, e.g.:
                    {"chart": True, "structure": True, "sector": True, "catalyst": False}
        conviction: 0-4 score
        notes:      Free-text explanation surfaced in the dashboard reasoning tab
        extra:      Any additional key/value pairs
    """
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path = _LOG_DIR / f"{today}.jsonl"

        record: dict = {
            "ts":        datetime.now(timezone.utc).isoformat(),
            "agent":     agent,
            "event":     event,
            "symbol":    symbol,
            "action":    action,
        }
        if corners is not None:
            record["corners"] = corners
        if conviction is not None:
            record["conviction"] = conviction
        if notes:
            record["notes"] = notes
        if extra:
            record.update(extra)

        with open(log_path, "a") as f:
            # json.dumps doesn't handle numpy scalars.  Convert them to native
            # Python types: integers before booleans (bool is a subclass of int,
            # and numpy.int64 must not be cast to bool).
            def _default(o):
                try:
                    import numpy as _np
                    if isinstance(o, _np.integer): return int(o)
                    if isinstance(o, _np.floating): return float(o)
                    if isinstance(o, _np.bool_): return bool(o)
                except ImportError:
                    pass
                return str(o)
            f.write(json.dumps(record, default=_default) + "\n")

        # Broadcast to live dashboard (import here to avoid circular at module load)
        from app.services import agent_tracker
        agent_tracker.reasoning(
            symbol=symbol,
            agent=agent,
            corners=corners or {},
            conviction=conviction or 0,
            action=action,
            notes=notes,
        )

    except Exception as exc:
        logger.warning(f"reasoning_log.write_reasoning failed silently: {exc}")


def recent(limit: int = 50) -> list[dict]:
    """
    Return the most recent reasoning records across the last 7 days of log files.

    Previously only read today's file — this caused the reasoning tab and scanner
    feed to appear empty after a server restart or on days when no pipeline run
    had occurred yet today.
    """
    from datetime import date, timedelta
    entries: list[dict] = []
    today = datetime.now(timezone.utc).date()
    for days_back in range(7):
        d = today - timedelta(days=days_back)
        log_path = _LOG_DIR / f"{d.isoformat()}.jsonl"
        if not log_path.exists():
            continue
        try:
            with open(log_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass
    # Sort newest-first, return top N
    entries.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return entries[:limit]
