"""
Chat Log — shared message store for dashboard ↔ WhatsApp chat.

Used by:
  app/routes/chat.py     (outbound: dashboard → WhatsApp)
  app/routes/whatsapp.py (inbound: WhatsApp → dashboard)

Messages are stored in logs/chat/messages.jsonl and broadcast
over SSE so the dashboard Chat tab updates in real time.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_LOG_DIR = Path(__file__).resolve().parents[3] / "logs" / "chat"


def _log_path() -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR / "messages.jsonl"


def append(role: str, content: str, source: str = "dashboard") -> dict:
    """
    Write one message to the chat JSONL and broadcast it over SSE.

    Args:
        role:    "user" (from the human / WhatsApp) |
                 "assistant" (outbound from dashboard/bot)
        content: Message text
        source:  "whatsapp" | "dashboard"
    """
    msg = {
        "ts":      datetime.now(timezone.utc).isoformat(),
        "role":    role,
        "content": content,
        "source":  source,
    }
    try:
        with open(_log_path(), "a") as f:
            f.write(json.dumps(msg) + "\n")
    except Exception as e:
        logger.warning(f"chat_log.append write failed: {e}")

    # Broadcast to all SSE clients
    try:
        from app.services import agent_tracker
        agent_tracker.chat(
            role=msg["role"],
            content=msg["content"],
            source=msg["source"],
            ts=msg["ts"],
        )
    except Exception as e:
        logger.warning(f"chat_log.append SSE broadcast failed: {e}")

    return msg


def recent(limit: int = 60) -> list:
    """Return up to `limit` recent messages, newest first."""
    msgs: list = []
    path = _log_path()
    if not path.exists():
        return []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msgs.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"chat_log.recent read failed: {e}")
    return list(reversed(msgs[-limit:]))
