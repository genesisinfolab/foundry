"""Alpha Vantage API Client — sector performance, company overview, symbol search"""
import logging
import time
import httpx
from functools import lru_cache
from app.config import get_settings

logger = logging.getLogger(__name__)
BASE = "https://www.alphavantage.co/query"


class AlphaVantageClient:
    def __init__(self):
        self.key = get_settings().alpha_vantage_api_key
        self._last_call = 0.0
        self._min_interval = 12.0  # Free tier: 5 calls/min → 12s between calls
        self._cache: dict = {}

    def _get(self, params: dict) -> dict:
        # Rate limiting
        now = time.time()
        wait = self._min_interval - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)

        params["apikey"] = self.key
        cache_key = str(sorted(params.items()))
        if cache_key in self._cache:
            return self._cache[cache_key]

        resp = httpx.get(BASE, params=params, timeout=30)
        self._last_call = time.time()
        resp.raise_for_status()
        data = resp.json()

        if "Error Message" in data or "Note" in data:
            logger.warning(f"Alpha Vantage error: {data.get('Error Message') or data.get('Note')}")
            return {}

        self._cache[cache_key] = data
        return data

    def sector_performance(self) -> dict:
        """Get real-time and historical sector performance"""
        data = self._get({"function": "SECTOR"})
        return data

    def company_overview(self, symbol: str) -> dict:
        """Get company fundamentals: float, shares outstanding, market cap, etc."""
        data = self._get({"function": "OVERVIEW", "symbol": symbol})
        if not data:
            return {}
        return {
            "symbol": data.get("Symbol"),
            "name": data.get("Name"),
            "market_cap": float(data.get("MarketCapitalization", 0)),
            "shares_outstanding": float(data.get("SharesOutstanding", 0)),
            "float_shares": float(data.get("Float", 0)) if data.get("Float") else None,
            "avg_volume": float(data.get("50DayMovingAverage", 0)),  # Proxy
            "sector": data.get("Sector"),
            "industry": data.get("Industry"),
            "pe_ratio": float(data.get("PERatio", 0)) if data.get("PERatio") != "None" else None,
            "beta": float(data.get("Beta", 0)) if data.get("Beta") != "None" else None,
        }

    def symbol_search(self, keywords: str) -> list[dict]:
        """Search for symbols matching keywords"""
        data = self._get({"function": "SYMBOL_SEARCH", "keywords": keywords})
        matches = data.get("bestMatches", [])
        return [
            {
                "symbol": m.get("1. symbol"),
                "name": m.get("2. name"),
                "type": m.get("3. type"),
                "region": m.get("4. region"),
            }
            for m in matches
        ]
