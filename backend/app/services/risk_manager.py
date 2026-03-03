"""
Risk Manager — Step 7 of Newman Strategy

Handles:
- Stop losses (ATR-based, floor at -2%)
- Uptrend line exit (primary profit exit — mirrors the entry signal)
- Profit tiers (fallback when uptrend line hasn't formed yet)
- Theme exposure limits
- Position monitoring

Exit priority:
  1. ATR stop      — always active, floors the loss
  2. Uptrend break — primary exit; drawn through swing lows since entry,
                     fires when today's close is > 1 % below the line
  3. Profit tiers  — fallback only when < 2 troughs exist (< ~10 bars
                     post-entry); prevents indefinite holding with no signal
"""
import logging
import numpy as np
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.position import Position, PositionAction, PositionStatus
from app.models.alert import Alert
from app.integrations.alpaca_client import AlpacaClient
from app.services.notifier import notify_trade
from app.services.audit_log import write_pretrade
from app.services.reasoning_log import write_reasoning
from app.services import agent_tracker

logger = logging.getLogger(__name__)


def detect_uptrend_break(bars: list[dict]) -> tuple[bool, float]:
    """
    Return (broke_below, support_level).

    Draws a trendline through the swing lows of `bars` (the post-entry
    window) and checks if today's close is > 1 % below it.

    This is the mirror of breakout_scanner.detect_resistance_break():
      Entry  — close breaks ABOVE the resistance line drawn through highs.
      Exit   — close breaks BELOW the support line drawn through lows.

    Returns (False, 0.0) when fewer than 2 troughs are detectable, which
    signals that the trendline hasn't formed yet (caller falls back to tiers).
    """
    if len(bars) < 6:
        return False, 0.0

    # Use all bars except today to build the trendline, check against today
    window = bars[:-1]
    today  = bars[-1]

    lows = np.array([b["low"] for b in window])
    neighborhood = max(2, min(5, len(lows) // 10))

    troughs = [
        idx for idx in range(neighborhood, len(lows) - neighborhood)
        if lows[idx] == min(lows[idx - neighborhood: idx + neighborhood + 1])
    ]

    if len(troughs) < 2:
        return False, 0.0

    recent = troughs[-min(6, len(troughs)):]
    t_x = np.array(recent, dtype=float)
    t_y = lows[recent]

    slope, intercept = np.polyfit(t_x, t_y, 1)
    support = slope * len(window) + intercept

    broke_below = today["close"] < support * 0.99   # 1 % clearance
    return broke_below, max(support, 0.0)


def _parse_bar_ts(bar: dict) -> datetime:
    """Parse Alpaca bar timestamp to UTC-aware datetime."""
    ts = bar.get("timestamp", "")
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    ts = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def calculate_atr(bars: list[dict], period: int = 14) -> float:
    """Calculate ATR-14 from a list of OHLC bars"""
    if len(bars) < period + 1:
        return 0.0
    true_ranges = []
    for i in range(1, len(bars)):
        high = bars[i]["high"]
        low = bars[i]["low"]
        prev_close = bars[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    if not true_ranges:
        return 0.0
    # Use EMA (Wilder's smoothing) for ATR
    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


class RiskManager:
    def __init__(self):
        self.alpaca = AlpacaClient()
        self.settings = get_settings()

    def check_all_positions(self, db: Session) -> list[dict]:
        """Check all open positions for stop-loss or profit-taking triggers"""
        positions = db.query(Position).filter(Position.status == PositionStatus.OPEN).all()
        actions_taken = []

        agent_tracker.spawn("risk_manager", f"Checking {len(positions)} open positions")
        for pos in positions:
            try:
                agent_tracker.update("risk_manager", f"Checking {pos.symbol}")
                result = self._check_position(pos, db)
                if result:
                    actions_taken.append(result)
            except Exception as e:
                logger.warning(f"Risk check failed for {pos.symbol}: {e}")

        db.commit()
        agent_tracker.complete("risk_manager",
            f"Done — {len(actions_taken)} action(s) taken on {len(positions)} position(s)")
        return actions_taken

    def _check_position(self, pos: Position, db: Session) -> Optional[dict]:
        """Check a single position for risk triggers"""
        # Get current price
        try:
            snapshot = self.alpaca.get_snapshot(pos.symbol)
            current_price = snapshot.get("latest_trade_price", 0)
        except Exception:
            return None

        if not current_price or current_price <= 0:
            return None

        # Update position
        pos.current_price = current_price
        pos.market_value = pos.qty * current_price
        pnl_pct = (current_price - pos.avg_entry_price) / pos.avg_entry_price if pos.avg_entry_price > 0 else 0
        pos.unrealized_pnl_pct = pnl_pct
        pos.unrealized_pnl = (current_price - pos.avg_entry_price) * pos.qty
        pos.updated_at = datetime.now(timezone.utc)

        # ── ATR-Based Stop Loss ──────────────────────────
        # Recalculate ATR stop if not set or entry is fresh
        if pos.stop_loss_price is None or pos.stop_loss_price <= 0:
            try:
                bars = self.alpaca.get_bars(pos.symbol, days=20)
                if len(bars) >= 15:
                    atr = calculate_atr(bars)
                    if atr > 0:
                        atr_stop = pos.avg_entry_price - (1.5 * atr)
                        # Floor: ATR stop must not exceed -2% loss
                        floor_stop = pos.avg_entry_price * (1 + self.settings.stop_loss_pct)
                        pos.stop_loss_price = max(atr_stop, floor_stop)
                        logger.debug(f"ATR stop for {pos.symbol}: ${pos.stop_loss_price:.2f} (ATR={atr:.2f})")
            except Exception as e:
                logger.warning(f"ATR calculation failed for {pos.symbol}: {e}")

        # Use ATR-based stop if available, else fall back to percentage stop
        if pos.stop_loss_price and pos.stop_loss_price > 0:
            if current_price <= pos.stop_loss_price:
                return self._execute_stop_loss(pos, current_price, pnl_pct, db)
        elif pnl_pct <= self.settings.stop_loss_pct:
            return self._execute_stop_loss(pos, current_price, pnl_pct, db)

        # ── Uptrend line exit (primary profit exit) ──────────────────────────
        # Fetch bars since entry to build the rising support trendline.
        # Only fires when in profit — below that the ATR stop handles it.
        if pnl_pct > 0:
            try:
                all_bars = self.alpaca.get_bars(pos.symbol, days=90)
                entry_dt = pos.opened_at
                if entry_dt and entry_dt.tzinfo is None:
                    entry_dt = entry_dt.replace(tzinfo=timezone.utc)

                post_entry = (
                    [b for b in all_bars if _parse_bar_ts(b) >= entry_dt]
                    if entry_dt else all_bars[-30:]
                )

                if len(post_entry) >= 6:
                    broke, support = detect_uptrend_break(post_entry)
                    if broke:
                        return self._execute_trendline_exit(
                            pos, current_price, pnl_pct, support, db
                        )
                    if support > 0:
                        # Trendline formed and intact — hold, wait for break
                        logger.debug(
                            f"{pos.symbol}: uptrend support ${support:.2f} intact | "
                            f"price ${current_price:.2f} | P&L {pnl_pct:.2%}"
                        )
                        return None
            except Exception as e:
                logger.warning(f"Uptrend check failed for {pos.symbol}: {e}")

        # ── Profit tiers (fallback when trendline hasn't formed) ──────────────
        # Fires only when the uptrend trendline returned no signal — i.e.
        # the position is young and < 2 troughs are detectable.
        for i, target in enumerate(self.settings.profit_take_tiers):
            if pnl_pct >= target:
                existing_takes = db.query(PositionAction).filter(
                    PositionAction.position_id == pos.id,
                    PositionAction.action_type == "take_profit",
                ).count()
                if existing_takes <= i:
                    return self._execute_profit_take(pos, current_price, pnl_pct, i + 1, db)

        return None

    def _execute_trendline_exit(
        self,
        pos: Position,
        price: float,
        pnl_pct: float,
        support: float,
        db: Session,
    ) -> dict:
        """Close the full position when price breaks below the rising support trendline."""
        logger.info(
            f"TRENDLINE EXIT: {pos.symbol} @ ${price:.2f} broke below support "
            f"${support:.2f} | P&L {pnl_pct:.2%}"
        )

        write_reasoning(
            agent="risk_manager",
            event="trendline_exit",
            symbol=pos.symbol,
            action="exit",
            corners={"chart": True, "structure": False, "sector": True, "catalyst": False},
            conviction=2,
            notes=(
                f"Uptrend line broken: ${price:.2f} < support ${support:.2f} "
                f"({(price / support - 1) * 100:.1f}% below) | P&L {pnl_pct:.2%}"
            ),
        )

        write_pretrade(
            event="trendline_exit",
            symbol=pos.symbol,
            side="sell",
            qty=pos.qty,
            price=price,
            pnl_pct=pnl_pct,
            paper=self.settings.alpaca_paper,
            extra={
                "support_level": round(support, 4),
                "entry_price":   pos.avg_entry_price,
                "position_age_days": (
                    (datetime.now(timezone.utc) - pos.opened_at).days
                    if pos.opened_at else None
                ),
            },
        )

        try:
            order = self.alpaca.close_position(pos.symbol)
        except Exception as e:
            logger.error(f"Trendline exit order failed for {pos.symbol}: {e}")
            return {"symbol": pos.symbol, "action": "trendline_exit_failed", "error": str(e)}

        realized = (price - pos.avg_entry_price) * pos.qty
        pos.status       = PositionStatus.CLOSED
        pos.realized_pnl = realized
        pos.closed_at    = datetime.now(timezone.utc)

        action = PositionAction(
            position=pos,
            action_type="trendline_exit",
            qty=pos.qty,
            price=price,
            reason=(
                f"Uptrend line broken @ ${price:.2f} "
                f"(support ${support:.2f}) | P&L {pnl_pct:.2%}"
            ),
            alpaca_order_id=order.get("order_id"),
        )
        db.add(action)

        alert = Alert(
            alert_type="trendline_exit",
            symbol=pos.symbol,
            title=f"📉 Trendline Exit: {pos.symbol}",
            message=(
                f"Closed {pos.qty} shares @ ${price:.2f}. "
                f"Support broken (${support:.2f}). "
                f"P&L: {pnl_pct:.2%} (${realized:.2f})"
            ),
            severity="info" if pnl_pct > 0 else "warning",
        )
        db.add(alert)

        notify_trade(
            "TRENDLINE_EXIT",
            pos.symbol,
            f"Uptrend broken @ ${price:.2f} (support ${support:.2f}) | "
            f"P&L {pnl_pct:.2%} (${realized:.2f})",
        )
        return {
            "symbol":   pos.symbol,
            "action":   "trendline_exit",
            "support":  round(support, 4),
            "pnl_pct":  pnl_pct,
            "pnl_usd":  realized,
        }

    def _execute_stop_loss(self, pos: Position, price: float, pnl_pct: float, db: Session) -> dict:
        """Execute a stop-loss exit"""
        logger.info(f"STOP LOSS: {pos.symbol} at {pnl_pct:.2%}")

        write_reasoning(
            agent="risk_manager",
            event="stop_loss",
            symbol=pos.symbol,
            action="exit",
            corners={"chart": False, "structure": False, "sector": True, "catalyst": False},
            conviction=0,
            notes=f"Stop triggered @ ${price:.2f} | Entry ${pos.avg_entry_price:.2f} | P&L {pnl_pct:.2%}",
        )

        write_pretrade(
            event="stop_loss",
            symbol=pos.symbol,
            side="sell",
            qty=pos.qty,
            price=price,
            stop_price=pos.stop_loss_price,
            pnl_pct=pnl_pct,
            paper=self.settings.alpaca_paper,
            extra={"entry_price": pos.avg_entry_price, "position_age_days": (
                (datetime.now(timezone.utc) - pos.created_at).days
                if pos.created_at else None
            )},
        )

        try:
            order = self.alpaca.close_position(pos.symbol)
        except Exception as e:
            logger.error(f"Stop loss order failed for {pos.symbol}: {e}")
            return {"symbol": pos.symbol, "action": "stop_loss_failed", "error": str(e)}

        pos.status = PositionStatus.STOPPED_OUT
        pos.realized_pnl = (price - pos.avg_entry_price) * pos.qty
        pos.closed_at = datetime.now(timezone.utc)

        action = PositionAction(
            position=pos,
            action_type="stop_loss",
            qty=pos.qty,
            price=price,
            reason=f"Stop loss triggered at {pnl_pct:.2%}",
            alpaca_order_id=order.get("order_id"),
        )
        db.add(action)

        alert = Alert(
            alert_type="stop_loss",
            symbol=pos.symbol,
            title=f"🛑 Stop Loss: {pos.symbol}",
            message=f"Closed {pos.qty} shares @ ${price:.2f}. P&L: {pnl_pct:.2%} (${pos.realized_pnl:.2f})",
            severity="warning",
        )
        db.add(alert)

        notify_trade("STOP_LOSS", pos.symbol, f"Closed @ ${price:.2f}, P&L {pnl_pct:.2%} (${pos.realized_pnl:.2f})")
        return {"symbol": pos.symbol, "action": "stop_loss", "pnl_pct": pnl_pct, "pnl_usd": pos.realized_pnl}

    def _execute_profit_take(self, pos: Position, price: float, pnl_pct: float, tier: int, db: Session) -> dict:
        """Scale out a portion at profit target"""
        # Final tier closes the full remaining position; earlier tiers sell 33%
        if tier >= len(self.settings.profit_take_tiers):
            sell_qty = pos.qty
        else:
            sell_qty = max(1, int(pos.qty * 0.33))
        if sell_qty >= pos.qty:
            sell_qty = pos.qty  # Close entire position

        logger.info(f"PROFIT TAKE T{tier}: {pos.symbol} selling {sell_qty}/{pos.qty} at {pnl_pct:.2%}")

        write_reasoning(
            agent="risk_manager",
            event="profit_take",
            symbol=pos.symbol,
            action="exit",
            corners={"chart": True, "structure": True, "sector": True, "catalyst": False},
            conviction=tier,
            notes=f"Tier {tier} target reached @ {pnl_pct:.1%} | Selling {sell_qty}/{pos.qty} shares @ ${price:.2f}",
        )

        write_pretrade(
            event="profit_take",
            symbol=pos.symbol,
            side="sell",
            qty=sell_qty,
            price=price,
            pnl_pct=pnl_pct,
            paper=self.settings.alpaca_paper,
            extra={
                "tier": tier,
                "tier_target_pct": self.settings.profit_take_tiers[tier - 1] * 100,
                "entry_price": pos.avg_entry_price,
                "shares_remaining_after": pos.qty - sell_qty,
                "realized_usd": round((price - pos.avg_entry_price) * sell_qty, 2),
            },
        )

        try:
            order = self.alpaca.place_market_order(pos.symbol, sell_qty, "sell")
        except Exception as e:
            logger.error(f"Profit take order failed for {pos.symbol}: {e}")
            return {"symbol": pos.symbol, "action": "profit_take_failed", "error": str(e)}

        realized = (price - pos.avg_entry_price) * sell_qty
        pos.qty -= sell_qty
        pos.realized_pnl += realized
        pos.market_value = pos.qty * price

        if pos.qty <= 0:
            pos.status = PositionStatus.CLOSED
            pos.closed_at = datetime.now(timezone.utc)

        action = PositionAction(
            position=pos,
            action_type="take_profit",
            qty=sell_qty,
            price=price,
            reason=f"Profit tier {tier} ({self.settings.profit_take_tiers[tier-1]:.0%}): sold {sell_qty} shares",
            alpaca_order_id=order.get("order_id"),
        )
        db.add(action)

        alert = Alert(
            alert_type="profit_target",
            symbol=pos.symbol,
            title=f"💰 Profit T{tier}: {pos.symbol}",
            message=f"Sold {sell_qty} @ ${price:.2f}. Realized: ${realized:.2f}. Remaining: {pos.qty} shares",
            severity="info",
        )
        db.add(alert)

        notify_trade("PROFIT_TAKE", pos.symbol, f"T{tier}: sold {sell_qty} @ ${price:.2f}, realized ${realized:.2f}, P&L {pnl_pct:.2%}")
        return {"symbol": pos.symbol, "action": f"profit_take_t{tier}", "sold_qty": sell_qty, "realized": realized}

    def get_portfolio_summary(self, db: Session) -> dict:
        """Get current portfolio risk summary"""
        account = self.alpaca.get_account()
        positions = db.query(Position).filter(Position.status == PositionStatus.OPEN).all()

        # Theme exposure
        theme_exposure: dict[int, float] = {}
        for pos in positions:
            tid = pos.theme_id or 0
            theme_exposure[tid] = theme_exposure.get(tid, 0) + pos.market_value

        portfolio_value = account["portfolio_value"]

        return {
            "account": account,
            "open_positions": len(positions),
            "total_exposure": sum(pos.market_value for pos in positions),
            "theme_exposure": {
                tid: {"value": val, "pct": val / portfolio_value if portfolio_value else 0}
                for tid, val in theme_exposure.items()
            },
            "largest_position_pct": max(
                (pos.market_value / portfolio_value for pos in positions), default=0
            ) if portfolio_value else 0,
        }
