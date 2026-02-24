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

# ── Hardcoded sector stock universe (fallback when ETF API unavailable) ──────
# Covers the most common Newman themes. Stocks are small/mid-cap with tradeable float.
SECTOR_STOCKS: dict[str, list[str]] = {
    "cannabis": ["MSOS", "TLRY", "CGC", "ACB", "CRON", "SNDL", "GTBIF", "TCNNF", "CURLF", "AYRWF"],
    "clean_energy": ["ENPH", "SEDG", "FSLR", "RUN", "NOVA", "ARRY", "CSIQ", "MAXN", "SPWR", "SHLS"],
    "solar": ["ENPH", "SEDG", "FSLR", "RUN", "NOVA", "CSIQ", "MAXN", "SPWR", "ARRY", "SHLS"],
    "biotech": ["MRNA", "BNTX", "NVAX", "CRSP", "BEAM", "EDIT", "NTLA", "ALNY", "RXRX", "SGEN"],
    "genomics": ["CRSP", "BEAM", "EDIT", "NTLA", "RXRX", "PACB", "ILMN", "CDNA", "FATE", "BLUE"],
    "semiconductors": ["NVDA", "AMD", "SMCI", "MRVL", "ON", "WOLF", "AEHR", "CEVA", "SLAB", "DIOD"],
    "ev": ["RIVN", "LCID", "FSR", "SOLO", "WKHS", "RIDE", "GOEV", "NKLA", "ZEV", "BLNK"],
    "ev_charging": ["BLNK", "CHPT", "EVGO", "VLTA", "SBE", "SPNV", "CLII", "AMPE", "PTRA"],
    "ai_software": ["SOUN", "BBAI", "AITX", "GFAI", "CXAI", "TSSI", "INPX", "PERI", "OTRK", "BTBT"],
    "artificial_intelligence": ["SOUN", "BBAI", "AITX", "GFAI", "PLTR", "AI", "BBAI", "TSSI", "INPX"],
    "uranium": ["UEC", "UUUU", "DNN", "CCJ", "NXE", "URG", "BQSSF", "PALAF", "HPNNF", "LTBR"],
    "nuclear": ["UEC", "UUUU", "DNN", "CCJ", "NXE", "LTBR", "OKLO", "NNE", "SMR", "BWXT"],
    "robotics": ["RBOT", "ISRG", "IRBT", "LIDR", "OUST", "VNET", "ACMR", "MVIS", "AEYE"],
    "space": ["RKLB", "SPCE", "ASTS", "LUNR", "MNTS", "PL", "SATL", "KTOS", "AJRD"],
    "cybersecurity": ["CRWD", "S", "QLYS", "VRNS", "DDOG", "ZS", "TENB", "RDWR", "CYBE"],
    "defense": ["KTOS", "AVAV", "CACI", "LDOS", "BWXT", "DRS", "HWM", "TDG", "GD"],
    "crypto": ["MSTR", "COIN", "MARA", "RIOT", "CLSK", "BTBT", "CIFR", "IREN", "HUT"],
    "bitcoin": ["MSTR", "COIN", "MARA", "RIOT", "CLSK", "BTBT", "CIFR", "IREN", "HUT"],
    "3d_printing": ["DDD", "SSYS", "MKFG", "NNDM", "XONE", "DM", "VLD", "SHPW"],
    "psychedelics": ["CMPS", "ATAI", "MNT", "MNMD", "NUMI", "TRYP", "CYBN"],
    "weight_loss": ["HIMS", "NTRA", "WW", "RVNC", "GPCR", "PEPG", "NKTR"],
    "ozempic": ["HIMS", "NTRA", "WW", "RVNC", "GPCR", "PEPG", "NKTR"],
}

# Keywords that map to sectors (for fuzzy theme matching)
THEME_KEYWORD_MAP: dict[str, str] = {
    "cannabis": "cannabis", "marijuana": "cannabis", "legalization": "cannabis", "weed": "cannabis",
    "solar": "solar", "photovoltaic": "solar", "panel": "solar",
    "clean energy": "clean_energy", "renewable": "clean_energy", "wind": "clean_energy",
    "biotech": "biotech", "fda": "biotech", "approval": "biotech", "clinical": "biotech",
    "gene": "genomics", "crispr": "genomics", "genomics": "genomics",
    "semiconductor": "semiconductors", "chip": "semiconductors", "nvidia": "semiconductors",
    "electric vehicle": "ev", "ev ": "ev", "lithium": "ev", "battery": "ev",
    "charging": "ev_charging", "charger": "ev_charging",
    "artificial intelligence": "artificial_intelligence", "ai ": "ai_software", "llm": "ai_software",
    "uranium": "uranium", "nuclear": "nuclear", "reactor": "nuclear",
    "robot": "robotics", "automation": "robotics", "drone": "robotics",
    "space": "space", "satellite": "space", "launch": "space", "rocket": "space",
    "cyber": "cybersecurity", "ransomware": "cybersecurity", "hack": "cybersecurity",
    "defense": "defense", "military": "defense", "pentagon": "defense",
    "bitcoin": "bitcoin", "crypto": "crypto", "blockchain": "crypto", "ethereum": "crypto",
    "3d print": "3d_printing", "additive": "3d_printing",
    "psychedelic": "psychedelics", "psilocybin": "psychedelics", "mdma": "psychedelics",
    "weight loss": "weight_loss", "obesity": "weight_loss", "glp-1": "weight_loss", "ozempic": "ozempic",
    "acquisition": "biotech",  # M&A themes often hit biotech
    "partnership": "biotech",
    "approval": "biotech",
}

def _get_sector_stocks_for_theme(theme_name: str, keywords: list[str]) -> list[str]:
    """Match a theme to a hardcoded sector stock list using name + keywords."""
    theme_lower = theme_name.lower().replace("_", " ")
    # Direct name match
    for sector, stocks in SECTOR_STOCKS.items():
        if sector.replace("_", " ") in theme_lower or theme_lower in sector.replace("_", " "):
            return stocks
    # Keyword match
    all_text = " ".join([theme_lower] + [k.lower() for k in keywords])
    for keyword, sector in THEME_KEYWORD_MAP.items():
        if keyword in all_text and sector in SECTOR_STOCKS:
            return SECTOR_STOCKS[sector]
    # Catalyst themes — default to a broad universe of active small caps
    if any(x in theme_lower for x in ["catalyst", "acquisition", "partnership", "approval", "merger"]):
        # Mix of biotech + EV + AI (most common M&A/catalyst sectors)
        return (SECTOR_STOCKS["biotech"][:5] + SECTOR_STOCKS["ev"][:5] +
                SECTOR_STOCKS["ai_software"][:5] + SECTOR_STOCKS["semiconductors"][:5])
    return []


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

        # Method 5: Hardcoded sector universe (guaranteed fallback)
        # Kicks in when ETF APIs return nothing — maps theme name + keywords to known sector stocks
        if len(symbols) < 5:
            kws = json.loads(theme.keywords) if theme.keywords else []
            sector_stocks = _get_sector_stocks_for_theme(theme.name, kws)
            if sector_stocks:
                symbols.update(sector_stocks)
                logger.info(f"Used hardcoded sector stocks for {theme.name}: {len(sector_stocks)} candidates")

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
