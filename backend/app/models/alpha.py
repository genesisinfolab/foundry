"""Alpha Intel models — external source parsing and insight storage."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class AlphaSource(Base):
    """
    A registered external content source (YouTube video/stream, URL, RSS feed,
    or manual text). The scanner fetches and parses these on demand or on schedule.
    """
    __tablename__ = "alpha_sources"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(200), nullable=False)
    source_type = Column(String(20),  nullable=False)   # youtube | url | rss | text
    url         = Column(String(1000), nullable=True)
    active       = Column(Boolean, default=True)
    # When True, tickers from this source are forwarded to the watchlist automatically
    # without asking for chat approval each time.
    auto_approve = Column(Boolean, default=False)
    last_fetched = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    insights = relationship(
        "AlphaInsight", back_populates="source",
        cascade="all, delete-orphan", order_by="AlphaInsight.created_at.desc()"
    )


class AlphaInsight(Base):
    """
    One parsed + Claude-analyzed snapshot of an AlphaSource.
    Created each time a source is scanned.
    """
    __tablename__ = "alpha_insights"

    id              = Column(Integer, primary_key=True, index=True)
    source_id       = Column(Integer, ForeignKey("alpha_sources.id"), nullable=False)
    content_preview = Column(Text,    nullable=True)   # first 500 chars of raw text
    tickers         = Column(Text,    nullable=True)   # JSON: [{"symbol":"NVDA","sentiment":"bullish","note":"..."}]
    analysis        = Column(Text,    nullable=True)   # Claude's formatted breakdown
    sentiment       = Column(String(20), nullable=True)  # bullish | bearish | mixed | neutral
    raw_length      = Column(Integer, default=0)
    video_title     = Column(String(500), nullable=True)  # YouTube: video title / ID
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    source = relationship("AlphaSource", back_populates="insights")
