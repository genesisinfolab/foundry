"""Finnhub API Client — news, fundamentals, peers"""
import logging
import time
import httpx
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)
BASE = "https://finnhub.io/api/v1"


class FinnhubClient:
    def __init__(self):
        self.key = get_settings().finnhub_api_key
        self._last_call = 0.0
        self._min_interval = 1.0  # rate limit: 60/min

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        now = time.time()
        wait = self._min_interval - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        params = params or {}
        params["token"] = self.key
        resp = httpx.get(f"{BASE}{path}", params=params, timeout=15)
        self._last_call = time.time()
        resp.raise_for_status()
        return resp.json()

    # ── News ────────────────────────────────────────────────
    def market_news(self, category: str = "general", min_id: int = 0) -> list[dict]:
        """General market news"""
        return self._get("/news", {"category": category, "minId": min_id})

    def company_news(self, symbol: str, from_date: str, to_date: str) -> list[dict]:
        return self._get("/company-news", {"symbol": symbol, "from": from_date, "to": to_date})

    # ── Fundamentals ────────────────────────────────────────
    def company_profile(self, symbol: str) -> dict:
        return self._get("/stock/profile2", {"symbol": symbol})

    def basic_financials(self, symbol: str) -> dict:
        return self._get("/stock/metric", {"symbol": symbol, "metric": "all"})

    # ── Peers & Industry ────────────────────────────────────
    def peers(self, symbol: str) -> list[str]:
        return self._get("/stock/peers", {"symbol": symbol})

    # ── Earnings Calendar ───────────────────────────────────
    def earnings_calendar(self, from_date: str, to_date: str) -> dict:
        return self._get("/calendar/earnings", {"from": from_date, "to": to_date})

    # ── Sector Performance (via ETF) ────────────────────────
    def quote(self, symbol: str) -> dict:
        return self._get("/quote", {"symbol": symbol})
