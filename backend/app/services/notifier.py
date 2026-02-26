"""Trade notification service — Newman persona voice."""
import subprocess
import logging

logger = logging.getLogger(__name__)

WHATSAPP_NUMBER = "+18136193622"


def _send(msg: str):
    """Dispatch a message to WhatsApp with openclaw fallback."""
    # Primary: wacli
    try:
        result = subprocess.run(
            ["wacli", "send", "text", "--to", WHATSAPP_NUMBER, "--message", msg],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            logger.info(f"WhatsApp sent: {msg[:80]}...")
            return
        logger.warning(f"wacli failed (rc={result.returncode}): {result.stderr}")
    except Exception as e:
        logger.warning(f"wacli notification failed: {e}")

    # Fallback: openclaw system event
    try:
        subprocess.Popen(
            ["openclaw", "system", "event", "--text", msg, "--mode", "now"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        logger.warning(f"openclaw event failed: {e}")


def notify_trade(event_type: str, symbol: str, details: str):
    """
    Generic trade notification — used by legacy callers.
    Formats in Newman's terse, observation-first style.
    """
    msg = f"📊 *{event_type}* — {symbol}\n{details}"
    _send(msg)


def notify_entry(symbol: str, qty: int, price: float, stop: float,
                 theme: str = "", corners: int = 4):
    from app.services.newman_persona import format_entry
    msg = format_entry(symbol, qty, price, stop, theme=theme, corners=corners)
    _send(msg)


def notify_exit(symbol: str, qty: int, price: float, entry_price: float,
                reason: str = "Trade not acting right."):
    from app.services.newman_persona import format_exit
    msg = format_exit(symbol, qty, price, entry_price, reason=reason)
    _send(msg)


def notify_pyramid(symbol: str, level: int, add_qty: int, price: float,
                   total_qty: int, pnl_pct: float):
    from app.services.newman_persona import format_pyramid
    msg = format_pyramid(symbol, level, add_qty, price, total_qty, pnl_pct)
    _send(msg)


def notify_stop(symbol: str, qty: int, price: float, entry_price: float):
    from app.services.newman_persona import format_stop
    msg = format_stop(symbol, qty, price, entry_price)
    _send(msg)


def notify_scan_summary(themes: int, breakouts: int, trades: int):
    from app.services.newman_persona import format_scan_summary
    msg = format_scan_summary(themes, breakouts, trades)
    _send(msg)


def notify_saturation(symbol: str, theme: str):
    from app.services.newman_persona import format_saturation_warning
    msg = format_saturation_warning(symbol, theme)
    _send(msg)
