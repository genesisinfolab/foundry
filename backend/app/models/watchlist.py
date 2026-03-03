"""Watchlist models"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


# Association table for WatchlistItem ↔ Theme many-to-many relationship.
# Replaces the old watchlist_items.theme_id FK so one symbol can live in
# multiple themes without duplicate rows.
watchlist_item_themes = Table(
    "watchlist_item_themes",
    Base.metadata,
    Column("watchlist_item_id", Integer, ForeignKey("watchlist_items.id"), primary_key=True),
    Column("theme_id", Integer, ForeignKey("themes.id"), primary_key=True),
)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True)
    company_name = Column(String(200), nullable=True)

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

    # Many-to-many relationship with themes
    themes = relationship(
        "Theme",
        secondary="watchlist_item_themes",
        back_populates="watchlist_items",
    )

    # ── Backward-compat shims ────────────────────────────────────────────────
    # All existing call sites use item.theme or item.theme_id.  These properties
    # preserve that API so nothing else needs to change.

    @property
    def theme(self):
        """Primary theme: the highest-scored associated theme, or None."""
        if not self.themes:
            return None
        return max(self.themes, key=lambda t: t.score or 0.0)

    @property
    def theme_id(self):
        """ID of the primary theme (backward compat with old FK column)."""
        t = self.theme
        return t.id if t else None

    def __repr__(self):
        return f"<WatchlistItem {self.symbol} theme={self.theme_id} score={self.rank_score:.2f}>"
