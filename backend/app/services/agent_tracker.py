"""
Agent Tracker — live event bus for the dashboard

Tracks the running state of each service (agent) and broadcasts
SSE events to all connected dashboard clients.

All public functions are thread-safe so they can be called from
APScheduler threads, background threads, or async FastAPI handlers.

Usage:
    from app.services import agent_tracker

    agent_tracker.spawn("breakout_scanner", "Starting scan cycle")
    agent_tracker.update("breakout_scanner", "Scanning NVDA (3/28)")
    agent_tracker.complete("breakout_scanner", "28 symbols scanned, 2 signals")
"""
import json
import queue
import threading
from datetime import datetime, timezone
from typing import Optional

# ── Internal state ────────────────────────────────────────────────────────────

_lock = threading.Lock()

# name → {status, detail, last_run, last_action, error}
_agents: dict[str, dict] = {}

# One queue per connected SSE client.  _push() fans out to all of them.
_subscribers: list[queue.Queue] = []


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(obj):
    """Fallback serializer: converts numpy scalars and other non-standard types."""
    try:
        import numpy as _np
        if isinstance(obj, _np.bool_):    return bool(obj)
        if isinstance(obj, _np.integer):  return int(obj)
        if isinstance(obj, _np.floating): return float(obj)
    except ImportError:
        pass
    return str(obj)


def _push(event_type: str, data: dict) -> None:
    payload = json.dumps({"type": event_type, "ts": _now(), **data}, default=_json_default)
    with _lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass  # slow client — drop event rather than block


# ── Subscription (one queue per SSE client) ───────────────────────────────────

def subscribe() -> queue.Queue:
    """Return a new per-client event queue.  Call unsubscribe() on disconnect."""
    q: queue.Queue = queue.Queue(maxsize=200)
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


# ── Agent lifecycle ───────────────────────────────────────────────────────────

def spawn(name: str, detail: str = "") -> None:
    """Mark an agent as running and broadcast the event."""
    with _lock:
        _agents[name] = {
            "status":      "running",
            "detail":      detail,
            "last_run":    _now(),
            "last_action": None,
            "error":       None,
        }
    _push("agent_spin", {"agent": name, "status": "running", "detail": detail})


def update(name: str, detail: str) -> None:
    """Update an agent's current activity detail."""
    with _lock:
        if name in _agents:
            _agents[name]["detail"]      = detail
            _agents[name]["last_action"] = detail
    _push("agent_spin", {"agent": name, "status": "running", "detail": detail})


def complete(name: str, detail: str = "") -> None:
    """Mark an agent as idle after a successful run."""
    with _lock:
        if name in _agents:
            _agents[name]["status"]      = "idle"
            _agents[name]["detail"]      = detail
            _agents[name]["last_action"] = detail
            _agents[name]["error"]       = None
    _push("agent_spin", {"agent": name, "status": "idle", "detail": detail})


def error(name: str, detail: str) -> None:
    """Mark an agent as errored."""
    with _lock:
        if name in _agents:
            _agents[name]["status"] = "error"
            _agents[name]["detail"] = detail
            _agents[name]["error"]  = detail
    _push("agent_spin", {"agent": name, "status": "error", "detail": detail})


# ── Domain events ─────────────────────────────────────────────────────────────

def reasoning(
    symbol: str,
    agent: str,
    corners: dict,
    conviction: int,
    action: str,
    notes: str = "",
) -> None:
    """Broadcast a model reasoning / 4-corners decision event."""
    _push("reasoning", {
        "symbol":     symbol,
        "agent":      agent,
        "corners":    corners,
        "conviction": conviction,
        "action":     action,
        "notes":      notes,
    })


def chat(role: str, content: str, source: str, ts: str = "") -> None:
    """Broadcast a chat message to all SSE clients."""
    _push("chat_message", {
        "role":    role,
        "content": content,
        "source":  source,
        "ts":      ts or _now(),
    })


def position_update(positions: list[dict]) -> None:
    """Broadcast a fresh snapshot of open positions."""
    _push("position_update", {"positions": positions})


def metric_update(data: dict) -> None:
    """Broadcast updated session metrics."""
    _push("metric_update", data)


# ── Snapshot ──────────────────────────────────────────────────────────────────

def broadcast(event_type: str, data: dict) -> None:
    """General-purpose broadcast — push any typed event to all SSE clients."""
    _push(event_type, data)


def get_agents() -> dict:
    with _lock:
        return {k: dict(v) for k, v in _agents.items()}
