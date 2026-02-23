"""
Share Structure Checker — Step 3 of Newman Strategy

Filters watchlist for "clean" share structure:
- Float < 200M
- Price > $0.50
- Avg volume > 100k
- No obvious dilution flags
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.watchlist import WatchlistItem
from app.integrations.finnhub_client import FinnhubClient
from app.integrations.alpha_vantage_client import AlphaVantageClient

logger = logging.getLogger(__name__)


class StructureChecker:
    def __init__(self):
        self.finnhub = FinnhubClient()
        self.av = AlphaVantageClient()
        self.settings = get_settings()

    def check_all(self, db: Session) -> list[WatchlistItem]:
        """Check share structure for all active watchlist items"""
        items = db.query(WatchlistItem).filter(WatchlistItem.active == True).all()
        clean_items = []

        for item in items:
            passed, notes = self._check_structure(item)
            item.structure_clean = passed
            item.structure_notes = notes
            item.updated_at = datetime.now(timezone.utc)

            if passed:
                clean_items.append(item)
                item.rank_score = self._calculate_rank(item)
            else:
                logger.debug(f"{item.symbol} failed structure check: {notes}")

        db.commit()
        logger.info(f"Structure check: {len(clean_items)}/{len(items)} passed")
        return clean_items

    def check_single(self, item: WatchlistItem, db: Session) -> bool:
        """Check a single watchlist item"""
        passed, notes = self._check_structure(item)
        item.structure_clean = passed
        item.structure_notes = notes
        item.updated_at = datetime.now(timezone.utc)
        if passed:
            item.rank_score = self._calculate_rank(item)
        db.commit()
        return passed

    def _check_structure(self, item: WatchlistItem) -> tuple[bool, str]:
        """Run all structure checks, return (passed, notes)"""
        notes = []
        s = self.settings

        # Enrich with Alpha Vantage if missing data
        if not item.float_shares or not item.market_cap:
            try:
                overview = self.av.company_overview(item.symbol)
                if overview:
                    item.float_shares = item.float_shares or overview.get("shares_outstanding")
                    item.market_cap = item.market_cap or overview.get("market_cap")
            except Exception as e:
                notes.append(f"Could not fetch AV data: {e}")

        # Check 1: Float < 200M
        if item.float_shares and item.float_shares > s.max_float:
            notes.append(f"Float too high: {item.float_shares / 1e6:.0f}M > {s.max_float / 1e6:.0f}M")

        # Check 2: Price > $0.50
        if item.price and item.price < s.min_price:
            notes.append(f"Price too low: ${item.price:.2f} < ${s.min_price:.2f}")

        # Check 3: Average volume > 100k
        if item.avg_volume and item.avg_volume < s.min_avg_volume:
            notes.append(f"Volume too low: {item.avg_volume:.0f} < {s.min_avg_volume}")

        # Check 4: Must have some data to evaluate
        if not item.price and not item.float_shares:
            notes.append("Insufficient data to evaluate")

        passed = len(notes) == 0
        return passed, "; ".join(notes) if notes else "Clean structure"

    def _calculate_rank(self, item: WatchlistItem) -> float:
        """Calculate ranking score for prioritizing watchlist items"""
        score = 0.0

        # Prefer smaller floats (more explosive potential)
        if item.float_shares:
            if item.float_shares < 10_000_000:
                score += 0.3
            elif item.float_shares < 50_000_000:
                score += 0.2
            elif item.float_shares < 100_000_000:
                score += 0.1

        # Prefer higher volume (liquidity)
        if item.avg_volume:
            if item.avg_volume > 1_000_000:
                score += 0.2
            elif item.avg_volume > 500_000:
                score += 0.15
            elif item.avg_volume > 200_000:
                score += 0.1

        # Prefer stocks with catalysts
        if item.catalyst_type:
            score += 0.2

        # Prefer stocks near breakout
        if item.near_breakout:
            score += 0.3

        return score
