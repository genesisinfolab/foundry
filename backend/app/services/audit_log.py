"""
Pre-Trade Audit Log

Writes a JSONL record to logs/pretrade/YYYY-MM-DD.jsonl BEFORE every order fires.
Review this file after each session — especially before going live.
Never raises: a logging failure must never block a trade.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve relative to repo root (backend/app/services/ -> ../../../logs/pretrade/)
# parents[0]=services, [1]=app, [2]=backend, [3]=repo-root
_LOG_DIR = Path(__file__).resolve().parents[3] / "logs" / "pretrade"


def write_pretrade(
    event: str,
    symbol: str,
    side: str,
    qty: int,
    price: float,
    *,
    stop_price: float | None = None,
    pnl_pct: float | None = None,
    theme: str = "",
    corners: int | None = None,
    pyramid_level: int | None = None,
    portfolio_value: float | None = None,
    cash: float | None = None,
    position_current_value: float | None = None,
    checks: list[str] | None = None,
    paper: bool = True,
    extra: dict | None = None,
) -> None:
    """
    Write one pre-trade audit record.

    Args:
        event:                 "shotgun_entry" | "pyramid" | "stop_loss" | "profit_take"
        symbol:                Ticker symbol
        side:                  "buy" | "sell"
        qty:                   Shares being traded
        price:                 Estimated execution price
        stop_price:            Stop-loss level (entries only)
        pnl_pct:               Unrealised P&L at decision time (exits/pyramids)
        theme:                 Theme name driving the trade
        corners:               Newman four-corners score (0-4)
        pyramid_level:         Level being added (pyramids only)
        portfolio_value:       Total portfolio value at decision time
        cash:                  Available cash at decision time
        position_current_value: Current market value of existing position (pyramids)
        checks:                List of checks that passed before this order
        paper:                 Whether this is paper trading
        extra:                 Any additional key/value pairs to include
    """
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path = _LOG_DIR / f"{today}.jsonl"

        trade_usd = round(qty * price, 2)
        stop_pct = None
        if stop_price and price and price > 0:
            stop_pct = round((stop_price - price) / price * 100, 2)

        position_pct_of_portfolio = None
        if portfolio_value and portfolio_value > 0 and position_current_value is not None:
            position_pct_of_portfolio = round(
                (position_current_value + trade_usd) / portfolio_value * 100, 1
            )

        record: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "paper": paper,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": round(price, 4),
            "trade_usd": trade_usd,
        }

        if stop_price is not None:
            record["stop_price"] = round(stop_price, 4)
            record["stop_pct"] = stop_pct

        if pnl_pct is not None:
            record["pnl_pct"] = round(pnl_pct * 100, 2)

        if theme:
            record["theme"] = theme

        if corners is not None:
            record["corners"] = corners

        if pyramid_level is not None:
            record["pyramid_level"] = pyramid_level

        portfolio: dict = {}
        if portfolio_value is not None:
            portfolio["portfolio_value"] = round(portfolio_value, 2)
        if cash is not None:
            portfolio["cash"] = round(cash, 2)
        if position_pct_of_portfolio is not None:
            portfolio["position_pct"] = position_pct_of_portfolio
        if portfolio:
            record["portfolio"] = portfolio

        if checks:
            record["checks_passed"] = checks

        if extra:
            record.update(extra)

        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    except Exception as exc:
        # Never let audit logging block a trade
        logger.warning(f"audit_log.write_pretrade failed silently: {exc}")
