"""
Watchlist Builder — Step 2 of Newman Strategy

For each detected theme:
1. Find all stocks in that sector (ETF holdings, peers, symbol search)
2. Track catalysts (earnings, FDA dates, legislative dates)
3. Store in DB with metadata
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.theme import Theme
from app.models.watchlist import WatchlistItem
from app.integrations.finnhub_client import FinnhubClient
from app.integrations.alpha_vantage_client import AlphaVantageClient
from app.integrations.alpaca_client import AlpacaClient
from app.integrations.etf_holdings import ETFHoldingsClient

logger = logging.getLogger(__name__)

# Import SECTOR_ETFS mapping for cross-referencing theme names
from app.services.theme_detector import SECTOR_ETFS


class WatchlistBuilder:
    def __init__(self):
        self.finnhub = FinnhubClient()
        self.av = AlphaVantageClient()
        self.alpaca = AlpacaClient()
        s = get_settings()
        self.etf_holdings = ETFHoldingsClient(s.finnhub_api_key)

    def build_for_theme(self, theme: Theme, db: Session) -> list[WatchlistItem]:
        """Build watchlist for a detected theme"""
        logger.info(f"Building watchlist for theme: {theme.name}")

        # 1. Gather candidate symbols
        candidates = self._find_candidates(theme)
        logger.info(f"Found {len(candidates)} candidates for {theme.name}")

        # 2. For each candidate, add to watchlist
        items = []
        for symbol in candidates[:30]:  # Cap at 30 per theme
            try:
                item = self._create_or_update_item(symbol, theme, db)
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f"Failed to process {symbol}: {e}")

        db.commit()
        logger.info(f"Watchlist for {theme.name}: {len(items)} items")
        return items

    def _find_candidates(self, theme: Theme) -> list[str]:
        """Find candidate symbols for a theme"""
        symbols = set()

        # Method 1: Search by theme keywords via Alpha Vantage
        keywords = json.loads(theme.keywords) if theme.keywords else []
        for kw in keywords[:3]:  # Limit API calls
            try:
                results = self.av.symbol_search(kw)
                for r in results:
                    if r.get("region") == "United States" and r.get("type") == "Equity":
                        symbols.add(r["symbol"])
            except Exception as e:
                logger.warning(f"AV symbol search failed for '{kw}': {e}")

        # Method 2: Get peers of known stocks in the theme
        if symbols:
            seed = list(symbols)[:3]
            for sym in seed:
                try:
                    peers = self.finnhub.peers(sym)
                    symbols.update(peers[:10])
                except Exception as e:
                    logger.warning(f"Finnhub peers failed for {sym}: {e}")

        # Method 3: ETF holdings (from theme's related ETFs)
        related_etfs = json.loads(theme.related_etfs) if theme.related_etfs else []
        for etf in related_etfs[:5]:
            try:
                holdings = self.etf_holdings.get_holdings(etf)
                for h in holdings:
                    sym = h.get("symbol", "").replace(".", "-")
                    if sym and len(sym) <= 5 and sym.replace("-", "").isalpha():
                        symbols.add(sym)
            except Exception as e:
                logger.warning(f"ETF holdings failed for {etf}: {e}")

        # Method 4: SECTOR_ETFS mapping — if theme name matches a known sector
        matching_sector_etfs = SECTOR_ETFS.get(theme.name, [])
        for etf in matching_sector_etfs[:3]:
            try:
                holdings = self.etf_holdings.get_holdings(etf)
                for h in holdings:
                    sym = h.get("symbol", "").replace(".", "-")
                    if sym and len(sym) <= 5 and sym.replace("-", "").isalpha():
                        symbols.add(sym)
            except Exception as e:
                logger.warning(f"SECTOR_ETFS holdings failed for {etf}: {e}")

        return list(symbols)

    def _create_or_update_item(self, symbol: str, theme: Theme, db: Session) -> Optional[WatchlistItem]:
        """Create or update a watchlist item with fundamentals"""
        existing = db.query(WatchlistItem).filter(
            WatchlistItem.symbol == symbol,
            WatchlistItem.theme_id == theme.id,
        ).first()

        if existing and existing.active:
            return existing  # Already tracked

        # Get fundamentals from Finnhub
        try:
            profile = self.finnhub.company_profile(symbol)
            if not profile:
                return None
        except Exception:
            profile = {}

        # Get current price/volume from Alpaca
        try:
            bars = self.alpaca.get_bars(symbol, days=5)
            if bars:
                latest_price = bars[-1]["close"]
                recent_volume = sum(b["volume"] for b in bars) / len(bars)
            else:
                latest_price = None
                recent_volume = None
        except Exception:
            latest_price = None
            recent_volume = None

        item = existing or WatchlistItem(symbol=symbol, theme_id=theme.id)
        item.company_name = profile.get("name")
        item.market_cap = profile.get("marketCapitalization", 0) * 1_000_000 if profile.get("marketCapitalization") else None
        item.float_shares = profile.get("shareOutstanding", 0) * 1_000_000 if profile.get("shareOutstanding") else None
        item.shares_outstanding = item.float_shares  # Approximation
        item.price = latest_price
        item.avg_volume = recent_volume
        item.active = True
        item.updated_at = datetime.now(timezone.utc)

        if not existing:
            db.add(item)

        return item

    def refresh_watchlist(self, db: Session):
        """Refresh all active watchlist items with current data"""
        items = db.query(WatchlistItem).filter(WatchlistItem.active == True).all()
        for item in items:
            try:
                bars = self.alpaca.get_bars(item.symbol, days=5)
                if bars:
                    item.price = bars[-1]["close"]
                    item.avg_volume = sum(b["volume"] for b in bars) / len(bars)
                    item.updated_at = datetime.now(timezone.utc)
            except Exception as e:
                logger.warning(f"Failed to refresh {item.symbol}: {e}")
        db.commit()
