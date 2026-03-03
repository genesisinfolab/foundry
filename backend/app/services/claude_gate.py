"""
Claude Gate — Second quality check for entry signals.

Called only when the rules-based system already says "yes" to a breakout.
Claude reviews the signal and returns an approve/reject with reasoning.

Design constraints:
  - Never raises. A failure defaults to approve=True so rules-based
    execution continues unchanged.
  - Only called for genuine candidates (conviction >= 1).
  - Hard stops, kill switch, position limits, and SPY gate are NOT subject
    to Claude's veto. This is a qualitative filter only.
"""
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

import time
# Circuit breaker: after 3 consecutive API failures, reject trades until the
# next success resets it.  Prevents runaway approvals during an outage.
_cb_lock      = threading.Lock()
_cb_failures  = 0
_cb_open_until = 0.0   # epoch seconds; circuit is "open" (blocking) until this time
_CB_THRESHOLD = 3      # failures before tripping
_CB_COOLDOWN  = 300    # seconds circuit stays open (5 min)


def evaluate_trade(
    symbol: str,
    corners: dict,
    conviction: int,
    theme: str,
    price: float,
    signals: list,
    extra_context: str = "",
) -> dict:
    """
    Ask Claude to review an entry signal and return a go/no-go decision.

    Returns:
        {
            "approve": bool,
            "confidence": "high" | "medium" | "low",
            "reasoning": str,
            "risk_note": str,
        }
    """
    # Check circuit breaker before even attempting the API call
    global _cb_failures, _cb_open_until
    with _cb_lock:
        cb_open = time.time() < _cb_open_until
    if cb_open:
        logger.warning(f"Claude gate circuit open — rejecting {symbol} without API call")
        return {
            "approve": False,
            "confidence": "unknown",
            "reasoning": "Claude gate circuit breaker open (repeated failures). Skipping entry.",
            "risk_note": "Check ANTHROPIC_API_KEY and API status.",
        }

    try:
        import anthropic
        from app.services.newman_persona import SYSTEM_PROMPT
        from app.config import get_settings

        # Use key from settings/.env if set, otherwise fall back to ANTHROPIC_API_KEY env var
        api_key = get_settings().anthropic_api_key or None
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

        corners_str = "\n".join(
            f"  {k}: {'PASS ✓' if v else 'FAIL ✗'}" for k, v in corners.items()
        )
        signals_str = (
            "\n".join(f"  {i+1}. {s}" for i, s in enumerate(signals))
            if signals
            else "  (no detailed signal list)"
        )

        user_msg = (
            f"Review this breakout entry signal for the Newman strategy.\n\n"
            f"Symbol: {symbol}\n"
            f"Theme: {theme or 'unknown'}\n"
            f"Current Price: ${price:.2f}\n"
            f"Conviction Score: {conviction}/4\n\n"
            f"Four Corners:\n{corners_str}\n\n"
            f"Scanner Analysis:\n{signals_str}\n"
        )
        if extra_context:
            user_msg += f"\nAdditional Context:\n{extra_context}\n"
        user_msg += (
            "\nIs this a genuine Newman-style breakout worth entering? "
            "Is this early enough? Is the setup clean?\n\n"
            "Reply EXACTLY in this format (no extra text):\n"
            "DECISION: GO\n"
            "CONFIDENCE: high\n"
            "REASONING: (one sentence)\n"
            "RISK NOTE: (one sentence)"
        )

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=250,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        response_text = message.content[0].text.strip()
        logger.debug(f"Claude gate [{symbol}]: {response_text[:120]}")
        with _cb_lock:
            _cb_failures = 0   # reset on success
        return _parse_response(response_text)

    except Exception as e:
        with _cb_lock:
            _cb_failures += 1
            if _cb_failures >= _CB_THRESHOLD:
                _cb_open_until = time.time() + _CB_COOLDOWN
                logger.error(
                    f"Claude gate circuit breaker OPEN for {_CB_COOLDOWN}s "
                    f"after {_cb_failures} consecutive failures. Rejecting trades."
                )
            cb_open_now = time.time() < _cb_open_until
        logger.warning(
            f"Claude gate unavailable for {symbol} — "
            f"{'REJECTING (circuit open)' if cb_open_now else 'approving (rules-only)'}: {e}"
        )
        approve = not cb_open_now
        return {
            "approve": approve,
            "confidence": "unknown",
            "reasoning": f"Claude gate unavailable ({type(e).__name__}). {'Circuit open — rejected.' if not approve else 'Rules-only entry.'}",
            "risk_note": "",
        }


def _parse_response(text: str) -> dict:
    """Parse Claude's structured DECISION/CONFIDENCE/REASONING/RISK NOTE response."""
    result = {
        "approve": True,
        "confidence": "medium",
        "reasoning": "",
        "risk_note": "",
    }
    for line in text.splitlines():
        line = line.strip()
        upper = line.upper()
        if upper.startswith("DECISION:"):
            val = line.split(":", 1)[1].strip().upper()
            result["approve"] = "NO-GO" not in val and "NO GO" not in val
        elif upper.startswith("CONFIDENCE:"):
            val = line.split(":", 1)[1].strip().lower()
            if val in ("high", "medium", "low"):
                result["confidence"] = val
        elif upper.startswith("REASONING:"):
            result["reasoning"] = line.split(":", 1)[1].strip()
        elif upper.startswith("RISK NOTE:"):
            result["risk_note"] = line.split(":", 1)[1].strip()

    # Fallback: use raw text as reasoning if parsing missed it
    if not result["reasoning"]:
        result["reasoning"] = text[:200]

    return result
