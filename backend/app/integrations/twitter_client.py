"""Twitter/X API Client — sentiment and trending topics"""
import logging
import httpx
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)
BASE = "https://api.twitter.com/2"


class TwitterClient:
    def __init__(self):
        s = get_settings()
        self.bearer = s.twitter_bearer_token
        self._headers = {"Authorization": f"Bearer {self.bearer}"}

    def search_recent(self, query: str, max_results: int = 50) -> list[dict]:
        """Search recent tweets (7-day window)"""
        try:
            resp = httpx.get(
                f"{BASE}/tweets/search/recent",
                params={
                    "query": query,
                    "max_results": min(max_results, 100),
                    "tweet.fields": "created_at,public_metrics,lang",
                },
                headers=self._headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.warning(f"Twitter search failed for '{query}': {e}")
            return []

    def get_stock_buzz(self, symbol: str) -> dict:
        """Get tweet count and sentiment proxy for a stock ticker"""
        # Search for $SYMBOL cashtag
        tweets = self.search_recent(f"${symbol} lang:en", max_results=100)
        if not tweets:
            return {"symbol": symbol, "tweet_count": 0, "avg_likes": 0, "buzz_score": 0.0}

        total_likes = sum(t.get("public_metrics", {}).get("like_count", 0) for t in tweets)
        total_rts = sum(t.get("public_metrics", {}).get("retweet_count", 0) for t in tweets)
        count = len(tweets)

        buzz = count * 0.5 + total_likes * 0.3 + total_rts * 0.2
        return {
            "symbol": symbol,
            "tweet_count": count,
            "avg_likes": total_likes / count if count else 0,
            "avg_retweets": total_rts / count if count else 0,
            "buzz_score": min(buzz / 100, 1.0),  # Normalize to 0-1
        }

    def search_theme_mentions(self, keywords: list[str], max_results: int = 100) -> list[dict]:
        """Search for theme-related keywords to detect emerging topics"""
        query = " OR ".join(keywords[:5])  # Twitter limits OR clauses
        query += " lang:en -is:retweet"
        return self.search_recent(query, max_results)
