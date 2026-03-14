"""Position and trade models"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum

from app.database import Base


class PositionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    STOPPED_OUT = "stopped_out"


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True)
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=True)

    # Position details
    status = Column(String(20), default=PositionStatus.OPEN)
    side = Column(String(10), default="buy")
    avg_entry_price = Column(Float, default=0.0)
    current_price = Column(Float, default=0.0)
    qty = Column(Float, default=0.0)
    market_value = Column(Float, default=0.0)

    # P&L
    unrealized_pnl = Column(Float, default=0.0)
    unrealized_pnl_pct = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)

    # Newman strategy tracking
    pyramid_level = Column(Integer, default=0)  # 0=starter, 1-4=pyramid tiers
    cost_basis = Column(Float, default=0.0)
    stop_loss_price = Column(Float, nullable=True)

    # Strategy identifier (newman | golden)
    strategy = Column(String(20), default="newman")

    # Alpaca order tracking
    alpaca_order_id = Column(String(100), nullable=True)

    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    actions = relationship("PositionAction", back_populates="position", cascade="all, delete-orphan")
    theme   = relationship("Theme", foreign_keys=[theme_id], lazy="joined")

    def __repr__(self):
        return f"<Position {self.symbol} qty={self.qty} pnl={self.unrealized_pnl_pct:.1%}>"


class PositionAction(Base):
    __tablename__ = "position_actions"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    action_type = Column(String(20))  # buy, sell, pyramid, stop_loss, take_profit
    qty = Column(Float, default=0.0)
    price = Column(Float, default=0.0)
    reason = Column(Text, nullable=True)
    alpaca_order_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    position = relationship("Position", back_populates="actions")
