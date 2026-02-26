"""Trade notification service"""
import subprocess
import logging

logger = logging.getLogger(__name__)

WHATSAPP_NUMBER = "+18136193622"

def notify_trade(event_type: str, symbol: str, details: str):
    msg = f"📊 *{event_type}*: {symbol} — {details}"

    # Primary: send directly to WhatsApp via wacli
    try:
        result = subprocess.run(
            ["wacli", "send", "text", "--to", WHATSAPP_NUMBER, "--message", msg],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            logger.info(f"WhatsApp notification sent: {msg}")
        else:
            logger.warning(f"wacli failed (rc={result.returncode}): {result.stderr}")
    except Exception as e:
        logger.warning(f"wacli notification failed: {e}")

    # Fallback: openclaw system event (triggers heartbeat wake)
    try:
        subprocess.Popen(
            ["openclaw", "system", "event", "--text", msg, "--mode", "now"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        logger.warning(f"openclaw event failed: {e}")
