"""
Newman Persona — The baseline agent identity for all strategy runs.

This module is the single source of truth for who the bot is.
Every decision, every alert, every log entry should be filtered through this lens.

Identity source: NEWMAN_IDENTITY.md (compiled Feb 2026)
Subject: Jeffrey Newman — $2,500 → $50M, 17 years, <50% win rate, always early.
"""
import os
import logging

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────
# Injected into any LLM context or used as the identity baseline for rule-based logic.

SYSTEM_PROMPT = """You are the Newman Trading Bot — a disciplined, early-stage thematic trader modeled
on the methodology and psychology of Jeffrey Newman.

Your operating identity:
- You trade themes, not tickers. You are always asking: what sector is about to move?
- You require all four corners before adding size: right chart, clean structure,
  right sector, defined catalyst. Missing a corner = nibble only.
- You exit instantly when a trade isn't working. You do not average down. You do not
  remember the loss. You move to the next opportunity.
- You pyramid into winners, never into losers.
- Your win rate is below 50%. This is expected and fine. You need 10-to-1 on winners.
- You never short. You never take outside capital. You operate alone.
- You watch for saturation: when a theme reaches non-specialists, you exit.
- You do not broadcast, seek validation, or ask for opinions. You observe and act.
- Privacy is an edge. Confidence does not require an audience.

When evaluating any trade:
1. Is this early? (Is the crowd already here?)
2. Are all four corners present?
3. What is the immediate exit level if wrong?
4. What does the full pyramid look like if right?

When a trade fails:
- Exit immediately.
- Log it as data, not failure.
- Move to next scan.

Your model: Jeffrey Newman. $2,500 → $50M in 17 years. <50% win rate. 80% avg annual
compounding. One-man operation. Never shorted. Never took outside capital. Always early."""


# ── Four Corners Logic ────────────────────────────────────────────────────────

def score_corners(
    chart_breakout: bool,
    structure_clean: bool,
    sector_active: bool,
    catalyst_present: bool,
) -> int:
    """Return how many of the four corners are confirmed (0-4)."""
    return sum([chart_breakout, structure_clean, sector_active, catalyst_present])


def position_size_for_corners(corners: int, starter_usd: float) -> float:
    """
    Newman sizing protocol:
      0 corners → no position
      1-2 corners → nibble only (starter)
      3 corners → half position
      4 corners → full position (pyramid when confirmed)
    """
    if corners == 0:
        return 0.0
    if corners <= 2:
        return starter_usd
    if corners == 3:
        return starter_usd * 2.0
    return starter_usd  # 4 corners → start at nibble, pyramid on confirmation


# ── Alert Formatting ──────────────────────────────────────────────────────────
# All outbound messages are written in Newman's voice:
# terse, observation-first, confident, no padding.

def format_entry(symbol: str, qty: int, price: float, stop: float,
                 theme: str = "", corners: int = 4, extra: str = "") -> str:
    """Format a Newman-style entry alert."""
    lines = [f"📊 *ENTRY* — {symbol}"]
    if theme:
        lines.append(f"{theme} theme active.")
    lines.append(f"Bought {qty} shares @ ${price:.2f} = ${qty * price:,.0f}.")
    lines.append(f"Stop: ${stop:.2f}. Corners: {corners}/4.")
    if extra:
        lines.append(extra)
    lines.append("Watching for volume confirmation to add.")
    return "\n".join(lines)


def format_exit(symbol: str, qty: int, price: float, entry_price: float,
                reason: str = "Trade not acting right.") -> str:
    """Format a Newman-style exit alert."""
    pnl = (price - entry_price) * qty
    pnl_pct = (price - entry_price) / entry_price * 100
    sign = "+" if pnl >= 0 else ""
    lines = [
        f"📊 *EXIT* — {symbol}",
        f"{reason}",
        f"Out @ ${price:.2f}. P&L: {sign}${pnl:,.0f} ({sign}{pnl_pct:.1f}%).",
        "Looking for next setup.",
    ]
    return "\n".join(lines)


def format_pyramid(symbol: str, level: int, add_qty: int, price: float,
                   total_qty: int, pnl_pct: float) -> str:
    """Format a Newman-style pyramid alert."""
    lines = [
        f"📊 *PYRAMID L{level}* — {symbol}",
        f"Volume confirming. Adding {add_qty} shares @ ${price:.2f}.",
        f"Total: {total_qty} shares. P&L: +{pnl_pct:.1f}%. Theme still early.",
    ]
    return "\n".join(lines)


def format_stop(symbol: str, qty: int, price: float, entry_price: float) -> str:
    """Format a Newman-style hard stop alert."""
    pnl = (price - entry_price) * qty
    pnl_pct = (price - entry_price) / entry_price * 100
    lines = [
        f"📊 *STOP HIT* — {symbol}",
        f"Hard stop triggered @ ${price:.2f}. Loss: ${pnl:,.0f} ({pnl_pct:.1f}%).",
        "Out. Not my puzzle today. Moving on.",
    ]
    return "\n".join(lines)


def format_scan_summary(themes: int, breakouts: int, trades: int) -> str:
    """Format a scan cycle summary in Newman's style."""
    return (
        f"📊 *Scan complete.* "
        f"{themes} theme(s) active. "
        f"{breakouts} breakout(s) detected. "
        f"{trades} order(s) placed."
    )


def format_saturation_warning(symbol: str, theme: str) -> str:
    """Format a saturation exit warning."""
    return (
        f"📊 *SATURATION* — {symbol}\n"
        f"{theme} theme reaching non-specialists. Edge expiring.\n"
        "Scaling out. Don't need the last 10%."
    )


# ── Persona Metadata ──────────────────────────────────────────────────────────

PERSONA_NAME = "newman"
PERSONA_VERSION = "1.0.0"
PERSONA_DESCRIPTION = (
    "Jeffrey Newman — disciplined thematic trader. "
    "$2,500 → $50M, 17 years, <50% win rate. Always early. Never short."
)


def describe() -> dict:
    """Return a summary of the active persona for logging/status endpoints."""
    return {
        "name": PERSONA_NAME,
        "version": PERSONA_VERSION,
        "description": PERSONA_DESCRIPTION,
        "corners_required_for_full_size": 4,
        "max_pyramid_levels": 4,
        "starter_position": "nibble (default $2,500)",
        "exit_rule": "instant — no grief, no averaging down",
        "win_rate_target": "<50% — asymmetric sizing compensates",
        "max_single_position": "35% of portfolio",
        "shorts": False,
        "outside_capital": False,
    }
