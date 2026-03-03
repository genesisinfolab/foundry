"""
Kill switch — thread-safe global pause flag for the Newman trading engine.

Set via:
  - WhatsApp PAUSE / STOP commands  (routes/whatsapp.py)
  - Dashboard STOP ALL button       (routes/dashboard.py)

Checked by trade_executor.shotgun_entry() before placing any new order.
"""
import threading
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_lock   = threading.Lock()
_paused = False
_reason = ""
_since: str | None = None


def is_paused() -> bool:
    with _lock:
        return _paused


def pause(reason: str = "Manual override") -> None:
    global _paused, _reason, _since
    with _lock:
        _paused = True
        _reason = reason
        _since  = datetime.now(timezone.utc).isoformat()
    logger.warning(f"KILL SWITCH: engine PAUSED — {reason}")
    try:
        from app.services import agent_tracker
        agent_tracker.metric_update("kill_switch", {"paused": True, "reason": reason})
    except Exception:
        pass


def resume() -> None:
    global _paused, _reason, _since
    with _lock:
        _paused = False
        _reason = ""
        _since  = None
    logger.info("KILL SWITCH: engine RESUMED")
    try:
        from app.services import agent_tracker
        agent_tracker.metric_update("kill_switch", {"paused": False})
    except Exception:
        pass


def status() -> dict:
    with _lock:
        return {"paused": _paused, "reason": _reason, "since": _since}
