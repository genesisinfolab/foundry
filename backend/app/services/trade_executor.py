"""
Trade Executor — Steps 5-6 of Newman Strategy

Handles:
- Shotgun entries (small starter positions across theme)
- Pyramiding into winners
- All trades via Alpaca paper trading
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.position import Position, PositionAction, PositionStatus
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert
from app.integrations.alpaca_client import AlpacaClient
from app.services.risk_manager import calculate_atr

logger = logging.getLogger(__name__)


class TradeExecutor:
    def __init__(self):
        self.alpaca = AlpacaClient()
        self.settings = get_settings()

    def shotgun_entry(self, item: WatchlistItem, db: Session) -> Optional[Position]:
        """
        Place a small starter position (Newman's 'shotgun' approach).
        Buy a small amount to have skin in the game.
        """
        s = self.settings

        # Check if we already have a position
        existing = db.query(Position).filter(
            Position.symbol == item.symbol,
            Position.status == PositionStatus.OPEN,
        ).first()
        if existing:
            logger.info(f"Already have position in {item.symbol}")
            return existing

        # Check account buying power
        account = self.alpaca.get_account()
        if account["cash"] < s.starter_position_usd:
            logger.warning(f"Insufficient cash for starter: ${account['cash']:.2f}")
            return None

        # Calculate shares to buy
        if not item.price or item.price <= 0:
            return None
        qty = int(s.starter_position_usd / item.price)
        if qty < 1:
            return None

        # Place order
        try:
            order = self.alpaca.place_market_order(item.symbol, qty, "buy")
        except Exception as e:
            logger.error(f"Order failed for {item.symbol}: {e}")
            return None

        # Record position
        position = Position(
            symbol=item.symbol,
            theme_id=item.theme_id,
            status=PositionStatus.OPEN,
            side="buy",
            avg_entry_price=item.price,
            current_price=item.price,
            qty=qty,
            market_value=qty * item.price,
            cost_basis=qty * item.price,
            pyramid_level=0,
            stop_loss_price=item.price * (1 + s.stop_loss_pct),
            alpaca_order_id=order.get("order_id"),
        )
        db.add(position)

        # Record action
        action = PositionAction(
            position=position,
            action_type="buy",
            qty=qty,
            price=item.price,
            reason=f"Shotgun entry for theme: {item.theme.name if item.theme else 'unknown'}",
            alpaca_order_id=order.get("order_id"),
        )
        db.add(action)

        # Create alert
        alert = Alert(
            alert_type="trade_entry",
            symbol=item.symbol,
            title=f"🎯 Shotgun Entry: {item.symbol}",
            message=f"Bought {qty} shares @ ~${item.price:.2f} = ${qty * item.price:.2f}",
            severity="info",
        )
        db.add(alert)

        db.commit()
        logger.info(f"ENTRY: {item.symbol} — {qty} shares @ ${item.price:.2f}")
        return position

    def check_pyramid(self, position: Position, db: Session) -> Optional[PositionAction]:
        """
        Check if we should pyramid into a winning position.
        Newman: scale in if up 3%+ with continued volume.
        """
        s = self.settings

        if position.pyramid_level >= s.max_pyramid_levels:
            return None

        # Get current data
        try:
            snapshot = self.alpaca.get_snapshot(position.symbol)
            current_price = snapshot.get("latest_trade_price", 0)
        except Exception:
            return None

        if not current_price or current_price <= 0:
            return None

        # Calculate P&L
        pnl_pct = (current_price - position.avg_entry_price) / position.avg_entry_price
        position.current_price = current_price
        position.unrealized_pnl_pct = pnl_pct
        position.unrealized_pnl = (current_price - position.avg_entry_price) * position.qty

        # Pyramid tiers: 3% profit = tier 1, 8% = tier 2, 15% = tier 3
        pyramid_thresholds = [0.03, 0.08, 0.15, 0.25]
        next_level = position.pyramid_level + 1
        if next_level > len(pyramid_thresholds):
            return None

        threshold = pyramid_thresholds[position.pyramid_level]
        if pnl_pct < threshold:
            db.commit()
            return None

        # Check theme exposure limits
        account = self.alpaca.get_account()
        portfolio_value = account["portfolio_value"]

        # Position size per tier: 2%, 5%, 10%, 10% of portfolio
        tier_sizes = [0.02, 0.05, 0.10, 0.10]
        add_usd = portfolio_value * tier_sizes[min(position.pyramid_level, len(tier_sizes) - 1)]

        # Check max single position limit
        current_value = position.qty * current_price
        if (current_value + add_usd) / portfolio_value > s.max_single_position_pct:
            logger.info(f"Max position limit reached for {position.symbol}")
            db.commit()
            return None

        # Calculate shares to add
        add_qty = int(add_usd / current_price)
        if add_qty < 1:
            db.commit()
            return None

        # Place pyramid order
        try:
            order = self.alpaca.place_market_order(position.symbol, add_qty, "buy")
        except Exception as e:
            logger.error(f"Pyramid order failed for {position.symbol}: {e}")
            db.commit()
            return None

        # Update position
        total_cost = position.cost_basis + (add_qty * current_price)
        total_qty = position.qty + add_qty
        position.avg_entry_price = total_cost / total_qty
        position.qty = total_qty
        position.cost_basis = total_cost
        position.pyramid_level = next_level
        position.market_value = total_qty * current_price

        # Record action
        action = PositionAction(
            position=position,
            action_type="pyramid",
            qty=add_qty,
            price=current_price,
            reason=f"Pyramid level {next_level}: {pnl_pct:.1%} gain, adding ${add_usd:.0f}",
            alpaca_order_id=order.get("order_id"),
        )
        db.add(action)

        alert = Alert(
            alert_type="pyramid",
            symbol=position.symbol,
            title=f"📈 Pyramid L{next_level}: {position.symbol}",
            message=f"Added {add_qty} shares @ ${current_price:.2f}. Total: {total_qty} shares, P&L: {pnl_pct:.1%}",
            severity="info",
        )
        db.add(alert)

        db.commit()
        logger.info(f"PYRAMID L{next_level}: {position.symbol} +{add_qty} @ ${current_price:.2f}")
        return action
