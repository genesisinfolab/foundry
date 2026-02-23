"""Perigon News API Client"""
import logging
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)
BASE = "https://api.goperigon.com/v1"


class PerigonClient:
    def __init__(self):
        self.key = get_settings().perigon_api_key

    def search_news(self, query: str, days: int = 7, size: int = 50) -> list[dict]:
        """Search news articles by keyword"""
        try:
            resp = httpx.get(
                f"{BASE}/all",
                params={
                    "apiKey": self.key,
                    "q": query,
                    "from": f"now-{days}d",
                    "size": size,
                    "sortBy": "relevance",
                    "sourceGroup": "top100",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            articles = data.get("articles", [])
            return [
                {
                    "title": a.get("title"),
                    "description": a.get("description"),
                    "url": a.get("url"),
                    "source": a.get("source", {}).get("domain"),
                    "published_at": a.get("pubDate"),
                    "sentiment": a.get("sentiment"),
                }
                for a in articles
            ]
        except Exception as e:
            logger.warning(f"Perigon search failed for '{query}': {e}")
            return []

    def search_stock_news(self, symbol: str, days: int = 7) -> list[dict]:
        """Get recent news for a specific stock"""
        return self.search_news(f"${symbol} stock", days=days, size=20)
