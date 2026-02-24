"""ETF Holdings Scraper — find all stocks in a sector via ETF component data"""
import logging
import time
import httpx
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# Map sector ETFs to their holdings API endpoints
# Using multiple free sources for ETF holdings
HOLDINGS_SOURCES = {
    # Finnhub ETF holdings endpoint
    "finnhub": "https://finnhub.io/api/v1/etf/holdings",
}


class ETFHoldingsClient:
    def __init__(self, finnhub_key: str):
        self.finnhub_key = finnhub_key
        self._cache: dict[str, list[dict]] = {}
        self._last_call = 0.0

    def get_holdings(self, etf_symbol: str) -> list[dict]:
        """Get all holdings of an ETF"""
        if etf_symbol in self._cache:
            return self._cache[etf_symbol]

        # Rate limit
        now = time.time()
        wait = 1.0 - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)

        try:
            resp = httpx.get(
                HOLDINGS_SOURCES["finnhub"],
                params={"symbol": etf_symbol, "token": self.finnhub_key},
                timeout=15,
            )
            self._last_call = time.time()
            resp.raise_for_status()
            data = resp.json()
            holdings = data.get("holdings", [])

            result = [
                {
                    "symbol": h.get("symbol", ""),
                    "name": h.get("name", ""),
                    "percent": h.get("percent", 0),
                    "value": h.get("value", 0),
                    "shares": h.get("share", 0),
                }
                for h in holdings
                if h.get("symbol")
            ]
            self._cache[etf_symbol] = result
            logger.info(f"ETF {etf_symbol}: {len(result)} holdings")
            return result

        except Exception as e:
            logger.warning(f"Failed to get holdings for {etf_symbol}: {e}")
            return []

    def get_sector_stocks(self, etf_symbols: list[str], min_weight_pct: float = 0.1) -> list[str]:
        """Get all unique stock symbols across multiple sector ETFs"""
        all_symbols = set()
        for etf in etf_symbols:
            holdings = self.get_holdings(etf)
            for h in holdings:
                if h["percent"] >= min_weight_pct and h["symbol"]:
                    # Filter out non-equity holdings
                    sym = h["symbol"].replace(".", "-")  # Normalize
                    if len(sym) <= 5 and sym.isalpha():
                        all_symbols.add(sym)
        return list(all_symbols)

    def get_small_caps_in_sector(self, etf_symbols: list[str], max_weight_pct: float = 2.0) -> list[str]:
        """Get smaller holdings (likely small-caps) from sector ETFs.
        Newman targets small/micro caps — these are usually the lower-weight holdings."""
        small_caps = []
        for etf in etf_symbols:
            holdings = self.get_holdings(etf)
            for h in holdings:
                if 0.05 <= h["percent"] <= max_weight_pct and h["symbol"]:
                    sym = h["symbol"].replace(".", "-")
                    if len(sym) <= 5:
                        small_caps.append(sym)
        return list(set(small_caps))
