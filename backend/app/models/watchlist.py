"""Watchlist models"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True)
    company_name = Column(String(200), nullable=True)
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=True)

    # Fundamentals
    market_cap = Column(Float, nullable=True)
    float_shares = Column(Float, nullable=True)
    shares_outstanding = Column(Float, nullable=True)
    avg_volume = Column(Float, nullable=True)
    price = Column(Float, nullable=True)

    # Share structure check
    structure_clean = Column(Boolean, default=False)
    structure_notes = Column(Text, nullable=True)

    # Breakout readiness
    near_breakout = Column(Boolean, default=False)
    breakout_level = Column(Float, nullable=True)
    volume_ratio = Column(Float, nullable=True)  # current vol / avg vol

    # Catalyst tracking
    catalyst_type = Column(String(100), nullable=True)
    catalyst_date = Column(DateTime, nullable=True)
    catalyst_notes = Column(Text, nullable=True)

    # Scoring
    rank_score = Column(Float, default=0.0)

    # Status
    active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    theme = relationship("Theme", back_populates="watchlist_items")

    def __repr__(self):
        return f"<WatchlistItem {self.symbol} theme={self.theme_id} score={self.rank_score:.2f}>"
