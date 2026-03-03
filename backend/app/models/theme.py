"""Theme detection models"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum

from app.database import Base


class ThemeStatus(str, enum.Enum):
    EMERGING = "emerging"
    HOT = "hot"
    COOLING = "cooling"
    DEAD = "dead"


class Theme(Base):
    __tablename__ = "themes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=ThemeStatus.EMERGING)

    # Composite score = news*0.4 + social*0.3 + etf*0.3
    score = Column(Float, default=0.0)
    news_score = Column(Float, default=0.0)
    social_score = Column(Float, default=0.0)
    etf_score = Column(Float, default=0.0)

    # Keywords that define this theme
    keywords = Column(Text, nullable=True)  # JSON list stored as text

    # Related ETFs
    related_etfs = Column(Text, nullable=True)  # JSON list

    # Theme classification (regulatory_catalyst, technology_breakthrough, etc.)
    category = Column(String(100), nullable=True)

    # Saturation detection
    is_saturated = Column(Boolean, default=False)
    saturated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    sources = relationship("ThemeSource", back_populates="theme", cascade="all, delete-orphan")
    watchlist_items = relationship(
        "WatchlistItem",
        secondary="watchlist_item_themes",
        back_populates="themes",
    )

    def __repr__(self):
        return f"<Theme {self.name} score={self.score:.2f} status={self.status}>"


class ThemeSource(Base):
    __tablename__ = "theme_sources"

    id = Column(Integer, primary_key=True, index=True)
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=False)
    source_type = Column(String(50))  # news, twitter, reddit, etf
    source_name = Column(String(200))
    headline = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    sentiment = Column(Float, default=0.0)  # -1.0 to 1.0
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    theme = relationship("Theme", back_populates="sources")
