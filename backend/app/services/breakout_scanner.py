"""
Breakout Scanner — Step 4 of Newman Strategy

Monitors clean watchlist stocks for:
- Volume surge (2-3x 20-day average)
- Price breakout above downtrend or consolidation range
- Accumulation patterns (large block trades)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert
from app.integrations.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)


class BreakoutScanner:
    def __init__(self):
        self.alpaca = AlpacaClient()
        self.settings = get_settings()

    def scan_all(self, db: Session) -> list[dict]:
        """Scan all clean watchlist items for breakouts"""
        items = db.query(WatchlistItem).filter(
            WatchlistItem.active == True,
            WatchlistItem.structure_clean == True,
        ).all()

        breakouts = []
        for item in items:
            try:
                result = self.scan_single(item, db)
                if result and result.get("triggered"):
                    breakouts.append(result)
            except Exception as e:
                logger.warning(f"Breakout scan failed for {item.symbol}: {e}")

        logger.info(f"Breakout scan: {len(breakouts)} signals from {len(items)} stocks")
        return breakouts

    def scan_single(self, item: WatchlistItem, db: Session) -> Optional[dict]:
        """Scan a single stock for breakout signals"""
        bars = self.alpaca.get_bars(item.symbol, days=60)
        if len(bars) < 20:
            return None

        closes = np.array([b["close"] for b in bars])
        volumes = np.array([b["volume"] for b in bars])

        # Volume analysis
        avg_volume_20d = np.mean(volumes[-20:])
        current_volume = volumes[-1]
        vol_ratio = current_volume / avg_volume_20d if avg_volume_20d > 0 else 0

        # Price analysis
        current_price = closes[-1]
        high_20d = np.max(closes[-20:])
        low_20d = np.min(closes[-20:])
        range_20d = high_20d - low_20d
        consolidation_range = range_20d / current_price if current_price > 0 else 0

        # Downtrend detection (simple linear regression on 30-day closes)
        x = np.arange(min(30, len(closes)))
        y = closes[-len(x):]
        slope = np.polyfit(x, y, 1)[0] if len(x) > 1 else 0
        trend_direction = "up" if slope > 0 else "down"

        # ── Breakout Signals ────────────────────────────────
        signals = []
        triggered = False

        # Bearish volume filter
        price_change_pct = (closes[-1] - closes[-2]) / closes[-2] if len(closes) >= 2 else 0
        surge_threshold = self.settings.volume_surge_multiplier
        bearish_surge = vol_ratio >= surge_threshold and price_change_pct < -0.03

        # Signal 1: Volume surge
        if vol_ratio >= surge_threshold:
            if bearish_surge:
                signals.append(f"⚠️ Bearish volume surge: price down {price_change_pct:.1%} on {vol_ratio:.1f}x volume — skipping")
            else:
                signals.append(f"🔊 Volume surge: {vol_ratio:.1f}x avg ({current_volume:,.0f} vs {avg_volume_20d:,.0f})")
                triggered = True

        # Signal 2: Price breakout above 20-day high
        if current_price >= high_20d * 0.98:  # Within 2% of or above 20-day high
            signals.append(f"📈 Near/at 20-day high: ${current_price:.2f} (high: ${high_20d:.2f})")
            if vol_ratio >= 1.5:  # Needs some volume confirmation
                triggered = True

        # Signal 3: Breaking out of tight consolidation
        if consolidation_range < 0.10 and vol_ratio > 1.5:  # <10% range + volume
            signals.append(f"📦 Consolidation breakout: {consolidation_range:.1%} range with {vol_ratio:.1f}x volume")
            triggered = True



        # Signal 4: Downtrend reversal
        if trend_direction == "down" and current_price > closes[-5:].mean():
            # Was trending down but price is now above 5-day average
            if vol_ratio > 1.5:
                signals.append(f"🔄 Downtrend reversal: slope was negative, price recovering on volume")
                triggered = True

        # Signal 5: Accumulation (increasing volume over several days)
        if len(volumes) >= 5:
            recent_avg = np.mean(volumes[-3:])
            prior_avg = np.mean(volumes[-10:-3])
            if recent_avg > prior_avg * 1.5 and slope >= 0:
                signals.append(f"🧱 Accumulation: 3-day vol avg {recent_avg:,.0f} vs prior {prior_avg:,.0f}")

        # Update watchlist item
        item.volume_ratio = vol_ratio
        item.near_breakout = triggered
        item.breakout_level = high_20d
        item.price = current_price
        item.updated_at = datetime.now(timezone.utc)

        # Create alert if breakout triggered
        if triggered:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            existing = db.query(Alert).filter(
                Alert.symbol == item.symbol,
                Alert.alert_type.in_(["breakout", "volume_surge"]),
                Alert.created_at >= today_start,
            ).first()
            if existing:
                logger.debug(f"Skipping duplicate breakout alert for {item.symbol} — already alerted today")
            else:
                alert = Alert(
                    alert_type="breakout" if vol_ratio >= surge_threshold else "volume_surge",
                    symbol=item.symbol,
                    theme_name=item.theme.name if item.theme else None,
                    title=f"🚨 Breakout: {item.symbol}",
                    message="\n".join(signals),
                    severity="action",
                )
                db.add(alert)
                db.commit()
                logger.info(f"BREAKOUT: {item.symbol} — {'; '.join(signals)}")

        result = {
            "symbol": item.symbol,
            "triggered": triggered,
            "signals": signals,
            "price": current_price,
            "volume_ratio": vol_ratio,
            "trend": trend_direction,
            "consolidation_range": consolidation_range,
            "high_20d": high_20d,
        }
        return result
