"""
WhatsApp command receiver — minimum safety for live trading.

Accepts incoming messages via POST /api/whatsapp/webhook.
Only processes messages from the authorised phone number.

Commands (case-insensitive):
  STOP               — pause engine + close ALL open positions
  STOP ALL           — same as STOP
  STOP <SYMBOL>      — close one position
  CLOSE <SYMBOL>     — alias for STOP <SYMBOL>
  PAUSE              — pause new entries (keep existing positions open)
  RESUME             — re-enable new entries
  STATUS             — reply with live portfolio snapshot

Production setup (Fly.io):
  Configure UltraMsg webhook: Dashboard → Webhooks → set URL to
    https://foundry-backend.fly.dev/api/whatsapp/webhook
  UltraMsg sends JSON: {"event_type":"received","data":{"from":"18136193622","body":"STATUS"}}

To test manually:
  curl -X POST https://foundry-backend.fly.dev/api/whatsapp/webhook \
    -H 'Content-Type: application/json' \
    -d '{"from": "+18136193622", "text": "STATUS"}'
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.position import Position, PositionStatus
from app.services import kill_switch
from app.services.notifier import _send
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# Only accept commands from this number (the owner's phone)
_ALLOWED_SENDER = get_settings().whatsapp_number


def _extract(payload: dict) -> tuple[str, str]:
    """Return (sender, text) from wacli, UltraMsg, Twilio, or plain JSON payloads.

    UltraMsg format: {"event_type":"received","data":{"from":"18136193622","body":"STATUS"}}
    wacli/plain:     {"from":"+18136193622","text":"STATUS"}
    Twilio:          {"From":"+18136193622","Body":"STATUS"}
    """
    # UltraMsg nests data under "data" key
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        data = payload

    sender = (
        data.get("from")
        or data.get("From")
        or data.get("sender")
        or payload.get("from")
        or payload.get("From")
        or ""
    ).strip()

    # Normalize: strip whatsapp: prefix if present (some providers add it)
    sender = sender.removeprefix("whatsapp:").strip()

    text = (
        data.get("body")
        or data.get("text")
        or data.get("Body")
        or data.get("message")
        or payload.get("text")
        or payload.get("Body")
        or payload.get("body")
        or payload.get("message")
        or ""
    ).strip()
    return sender, text


@router.post("/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive incoming WhatsApp messages and execute control commands."""
    # ── Parse body (JSON or form-encoded) ────────────────────────────────────
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form    = await request.form()
            payload = dict(form)
    except Exception as e:
        logger.warning(f"WhatsApp webhook parse error: {e}")
        return {"status": "parse_error"}

    sender, text = _extract(payload)
    logger.info(f"WhatsApp inbound from {sender!r}: {text!r}")

    # ── Security: only the authorised number ─────────────────────────────────
    if sender and sender != _ALLOWED_SENDER:
        logger.warning(f"WhatsApp: ignored message from unauthorised sender {sender!r}")
        return {"status": "unauthorised"}

    # ── Log inbound to chat log (so dashboard Chat tab shows it) ─────────────
    if text:
        try:
            from app.services import chat_log
            chat_log.append(role="user", content=text, source="whatsapp")
        except Exception as _e:
            logger.warning(f"chat_log inbound append failed: {_e}")

    handle_command(text, db)
    return {"status": "ok"}


def handle_command(text: str, db) -> None:
    """
    Process a WhatsApp command text.  Called by both the webhook endpoint
    and the WhatsAppListener polling loop so the logic lives in one place.
    """
    cmd = text.upper().strip()

    # ── STOP / STOP ALL ───────────────────────────────────────────────────────
    if cmd in ("STOP", "STOP ALL"):
        kill_switch.pause(reason="WhatsApp STOP command")
        positions = db.query(Position).filter(
            Position.status == PositionStatus.OPEN
        ).all()
        from app.integrations.alpaca_client import AlpacaClient
        client = AlpacaClient()
        closed, errors = [], []
        for pos in positions:
            try:
                client.close_position(pos.symbol)
                pos.status    = PositionStatus.CLOSED
                pos.closed_at = datetime.now(timezone.utc)
                closed.append(pos.symbol)
            except Exception as e:
                errors.append(f"{pos.symbol}: {e}")
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"DB commit failed after STOP: {e}")
        msg = f"\U0001f6d1 STOPPED. Engine paused. Closed: {', '.join(closed) or 'none'}."
        if errors:
            msg += f" Errors: {'; '.join(errors)}"
        _send(msg)
        return

    # ── STOP <SYMBOL> / CLOSE <SYMBOL> ───────────────────────────────────────
    parts = cmd.split()
    if len(parts) == 2 and parts[0] in ("STOP", "CLOSE"):
        symbol = parts[1]
        pos = db.query(Position).filter(
            Position.symbol == symbol,
            Position.status == PositionStatus.OPEN,
        ).first()
        if not pos:
            _send(f"\u26a0\ufe0f No open position for {symbol}.")
            return
        try:
            from app.integrations.alpaca_client import AlpacaClient
            AlpacaClient().close_position(symbol)
            pos.status    = PositionStatus.CLOSED
            pos.closed_at = datetime.now(timezone.utc)
            db.commit()
            _send(f"\u2705 Closed {symbol}.")
        except Exception as e:
            db.rollback()
            _send(f"\u274c Failed to close {symbol}: {e}")
        return

    # ── PAUSE ─────────────────────────────────────────────────────────────────
    if cmd == "PAUSE":
        kill_switch.pause(reason="WhatsApp PAUSE command")
        _send("\u23f8 Engine paused — no new entries. Existing positions continue.")
        return

    # ── RESUME ────────────────────────────────────────────────────────────────
    if cmd == "RESUME":
        kill_switch.resume()
        _send("\u25b6\ufe0f Engine resumed — new entries re-enabled.")
        return

    # ── STATUS ────────────────────────────────────────────────────────────────
    if cmd == "STATUS":
        positions = db.query(Position).filter(
            Position.status == PositionStatus.OPEN
        ).all()
        ks = kill_switch.status()
        state = "\u23f8 PAUSED" if ks["paused"] else "\u25b6\ufe0f RUNNING"
        lines = [f"\U0001f4ca Newman — {state}"]
        lines.append(f"Open positions: {len(positions)}")
        for p in positions:
            pnl   = float(p.unrealized_pnl_pct or 0) * 100
            price = float(p.avg_entry_price or 0)
            lines.append(f"  {p.symbol}: {p.qty}sh @ ${price:.2f} | P&L {pnl:+.1f}%")
        if not positions:
            lines.append("  (none)")
        _send("\n".join(lines))
        return

    # ── KILL SWITCH STATUS ────────────────────────────────────────────────────
    if cmd in ("KS", "KILLSWITCH", "KILL"):
        ks = kill_switch.status()
        _send(f"Kill switch: {'PAUSED' if ks['paused'] else 'active'}. Send RESUME to re-enable.")
        return

    # ── Unknown command ───────────────────────────────────────────────────────
    if text:
        _send(
            f"\u2753 Unknown: {text!r}\n"
            "Commands: STOP, STOP <TICKER>, PAUSE, RESUME, STATUS"
        )


@router.get("/status")
def kill_switch_status():
    """REST endpoint: current kill switch state (for dashboard)."""
    return kill_switch.status()
