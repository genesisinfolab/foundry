"""Trade notification service — Newman persona voice."""
import subprocess
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


def _to_jid(number: str) -> str:
    """Convert +1XXXXXXXXXX phone number to wacli JID format (no + prefix, @s.whatsapp.net)."""
    clean = number.lstrip("+")
    if "@" not in clean:
        clean = f"{clean}@s.whatsapp.net"
    return clean


def _send(msg: str) -> bool:
    """Send WhatsApp notification. Returns True if delivered by any method."""
    number = get_settings().whatsapp_number
    if not number:
        logger.warning("WHATSAPP_NUMBER not configured — notification suppressed")
        return False

    # Primary: UltraMsg HTTP API (works from any server)
    ultramsg_instance = get_settings().ultramsg_instance_id
    ultramsg_token_val = get_settings().ultramsg_token
    if ultramsg_instance and ultramsg_token_val:
        try:
            import json as _json
            import urllib.request as _req
            phone = number if number.startswith("+") else f"+{number.lstrip('+')}"
            payload = _json.dumps({
                "token": ultramsg_token_val,
                "to": phone,
                "body": msg,
            }).encode()
            url = f"https://api.ultramsg.com/{ultramsg_instance}/messages/chat"
            request = _req.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            })
            with _req.urlopen(request, timeout=15) as resp:
                result = _json.loads(resp.read().decode())
                if str(result.get("sent", "")).lower() == "true":
                    logger.info(f"UltraMsg sent: {msg[:80]}...")
                    return True
                logger.warning(f"UltraMsg returned unexpected response: {result}")
        except Exception as e:
            logger.warning(f"UltraMsg notification failed: {e}")

    # Secondary: CallMeBot HTTP API (works from any server including Fly.io)
    callmebot_key = get_settings().callmebot_api_key
    if callmebot_key:
        try:
            import urllib.parse
            import urllib.request
            clean = number.lstrip("+").split("@")[0]
            url = (
                "https://api.callmebot.com/whatsapp.php"
                f"?phone={clean}&text={urllib.parse.quote(msg)}&apikey={callmebot_key}"
            )
            with urllib.request.urlopen(url, timeout=15) as resp:
                if resp.status == 200:
                    logger.info(f"CallMeBot sent: {msg[:80]}...")
                    return True
        except Exception as e:
            logger.warning(f"CallMeBot notification failed: {e}")

    # Fallback: wacli (local Mac only)
    jid = _to_jid(number)
    try:
        result = subprocess.run(
            ["wacli", "send", "text", "--to", jid, "--message", msg],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"WhatsApp sent (wacli): {msg[:80]}...")
            return True
        logger.warning(f"wacli failed (rc={result.returncode}): {result.stderr}")
    except FileNotFoundError:
        logger.debug("wacli not installed — skipping")
    except Exception as e:
        logger.warning(f"wacli notification failed: {e}")

    # Last resort: openclaw system event (local Mac only)
    try:
        result = subprocess.run(
            ["openclaw", "system", "event", "--text", msg, "--mode", "now"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            logger.info(f"Notification sent (openclaw): {msg[:80]}...")
            return True
    except FileNotFoundError:
        logger.debug("openclaw not installed — skipping")
    except Exception as e:
        logger.warning(f"openclaw event failed: {e}")

    logger.error("All notification methods failed — set ULTRAMSG_INSTANCE_ID + ULTRAMSG_TOKEN, or run locally with wacli/openclaw")
    return False


def notify_trade(event_type: str, symbol: str, details: str) -> bool:
    """
    Generic trade notification — used by legacy callers.
    Formats in Newman's terse, observation-first style.
    """
    msg = f"📊 *{event_type}* — {symbol}\n{details}"
    return _send(msg)


def notify_entry(symbol: str, qty: int, price: float, stop: float,
                 theme: str = "", corners: int = 4) -> bool:
    from app.services.newman_persona import format_entry
    msg = format_entry(symbol, qty, price, stop, theme=theme, corners=corners)
    return _send(msg)


def notify_exit(symbol: str, qty: int, price: float, entry_price: float,
                reason: str = "Trade not acting right.") -> bool:
    from app.services.newman_persona import format_exit
    msg = format_exit(symbol, qty, price, entry_price, reason=reason)
    return _send(msg)


def notify_pyramid(symbol: str, level: int, add_qty: int, price: float,
                   total_qty: int, pnl_pct: float) -> bool:
    from app.services.newman_persona import format_pyramid
    msg = format_pyramid(symbol, level, add_qty, price, total_qty, pnl_pct)
    return _send(msg)


def notify_stop(symbol: str, qty: int, price: float, entry_price: float) -> bool:
    from app.services.newman_persona import format_stop
    msg = format_stop(symbol, qty, price, entry_price)
    return _send(msg)


def notify_scan_summary(themes: int, breakouts: int, trades: int) -> bool:
    from app.services.newman_persona import format_scan_summary
    msg = format_scan_summary(themes, breakouts, trades)
    return _send(msg)


def notify_health_check(overall: str, fails: int, warns: int, fail_details: list[str],
                        warn_details: list[str] | None = None) -> bool:
    """Send health check summary to WhatsApp after each scan cycle."""
    if overall == "OK" and fails == 0 and warns == 0:
        msg = "✅ *Health Check* — All systems OK"
    else:
        icon = "🔴" if fails > 0 else "🟡"
        msg = f"{icon} *Health Check* — {overall} | FAIL:{fails} WARN:{warns}\n"
        details = (fail_details or []) + (warn_details or [])
        if details:
            msg += "\n".join(f"• {d}" for d in details[:4])
    return _send(msg)


def notify_saturation(symbol: str, theme: str) -> bool:
    from app.services.newman_persona import format_saturation_warning
    msg = format_saturation_warning(symbol, theme)
    return _send(msg)
