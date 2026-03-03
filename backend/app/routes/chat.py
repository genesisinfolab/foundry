"""
Chat Routes — unified dashboard ↔ WhatsApp chat interface.

GET  /api/chat/history   — recent messages (dashboard + WhatsApp, newest first)
POST /api/chat/send      — send a message (dashboard → WhatsApp + log)
"""
import logging

from fastapi import APIRouter

from app.services import chat_log
from app.services.notifier import _send as _whatsapp_send

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/history")
def get_history(limit: int = 60):
    """Return recent chat messages (newest first)."""
    return chat_log.recent(limit)


@router.post("/send")
async def send_message(body: dict):
    """
    Send a message from the dashboard.
    Logs it as a user message, checks for alpha proposal responses,
    then dispatches to WhatsApp.
    """
    from fastapi import Depends
    from app.database import SessionLocal

    content = str(body.get("content", "")).strip()
    if not content:
        return {"error": "empty message"}

    # Log as user message (dashboard operator)
    msg = chat_log.append(role="user", content=content, source="dashboard")

    # Check if this is a YES/NO/ALWAYS/REVOKE response to a pending alpha proposal
    try:
        from app.services.alpha_scanner import resolve_alpha_proposal
        db = SessionLocal()
        try:
            bot_reply = resolve_alpha_proposal(content, db)
            if bot_reply:
                chat_log.append(role="assistant", content=bot_reply, source="alpha_intel")
                from app.services import agent_tracker
                agent_tracker.chat(role="assistant", content=bot_reply, source="alpha_intel")
                return msg
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Alpha proposal resolution failed: {e}")

    # Dispatch to WhatsApp for normal messages
    try:
        _whatsapp_send(content)
    except Exception as e:
        logger.warning(f"Chat send to WhatsApp failed: {e}")

    return msg
