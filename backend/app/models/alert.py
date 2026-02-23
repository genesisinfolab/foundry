"""Alert models"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from datetime import datetime, timezone

from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String(50), index=True)  # breakout, volume_surge, stop_loss, profit_target, theme_detected
    symbol = Column(String(20), nullable=True, index=True)
    theme_name = Column(String(200), nullable=True)
    title = Column(String(300))
    message = Column(Text)
    severity = Column(String(20), default="info")  # info, warning, action, critical
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Alert {self.alert_type} {self.symbol or self.theme_name}>"
