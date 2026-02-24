"""Trade notification service"""
import subprocess, logging
logger = logging.getLogger(__name__)

def notify_trade(event_type: str, symbol: str, details: str):
    msg = f"{event_type}: {symbol} — {details}"
    try:
        subprocess.Popen(['openclaw', 'system', 'event', '--text', msg, '--mode', 'now'])
        logger.info(f"Notification sent: {msg}")
    except Exception as e:
        logger.warning(f"Notification failed: {e}")
