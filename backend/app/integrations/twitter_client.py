"""Twitter/X API Client — sentiment and trending topics

Notes on Basic tier limitations:
- Cashtag operator ($SYMBOL) is NOT available — use plain text queries instead
- Rate limit: 60 requests / 15 minutes (bearer token)
- We cap at 10 results per call to conserve quota
"""
import logging
import re
import time
import httpx
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)
BASE = "https://api.twitter.com/2"

# Rate limiter: track last call times to stay under 60/15min = 4/min
_last_call_times: list[float] = []
_RATE_LIMIT = 55  # Leave 5 buffer below 60
_RATE_WINDOW = 900  # 15 minutes in seconds


def _rate_limit_check():
    """Block briefly if we're approaching the rate limit window."""
    now = time.time()
    global _last_call_times
    # Remove calls older than 15 min
    _last_call_times = [t for t in _last_call_times if now - t < _RATE_WINDOW]
    if len(_last_call_times) >= _RATE_LIMIT:
        # Sleep until oldest call falls out of window
        sleep_secs = _RATE_WINDOW - (now - _last_call_times[0]) + 1
        logger.warning(f"Twitter rate limit reached — sleeping {sleep_secs:.0f}s")
        time.sleep(sleep_secs)
    _last_call_times.append(time.time())


def _strip_cashtag(query: str) -> str:
    """Remove $ prefix from ticker symbols — cashtag operator not available on Basic tier."""
    return re.sub(r'\$([A-Z]{1,5})\b', r'\1', query)


class TwitterClient:
    def __init__(self):
        s = get_settings()
        self.bearer = s.twitter_bearer_token
        self._headers = {"Authorization": f"Bearer {self.bearer}"}

    def search_recent(self, query: str, max_results: int = 10) -> list[dict]:
        """Search recent tweets (7-day window).

        Caps at 10 results by default to conserve rate limit quota.
        Strips cashtag operator ($) which is not available on Basic tier.
        """
        query = _strip_cashtag(query)
        # Ensure we have -is:retweet to reduce noise
        if "-is:retweet" not in query:
            query += " -is:retweet"
        # Clamp max_results: Twitter requires 10-100
        max_results = max(10, min(max_results, 100))

        try:
            _rate_limit_check()
            resp = httpx.get(
                f"{BASE}/tweets/search/recent",
                params={
                    "query": query,
                    "max_results": max_results,
                    "tweet.fields": "created_at,public_metrics,lang",
                },
                headers=self._headers,
                timeout=15,
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("retry-after", 60))
                logger.warning(f"Twitter 429 — sleeping {retry_after}s")
                time.sleep(retry_after)
                return []
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.warning(f"Twitter search failed for '{query}': {e}")
            return []

    def get_stock_buzz(self, symbol: str) -> dict:
        """Get tweet count and sentiment proxy for a stock ticker.

        Uses plain text search (no cashtag operator) for Basic tier compatibility.
        """
        # Use stock name as plain text, not cashtag
        tweets = self.search_recent(f"{symbol} stock lang:en", max_results=10)
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
            "buzz_score": min(buzz / 100, 1.0),
        }

    def search_theme_mentions(self, keywords: list[str], max_results: int = 10) -> list[dict]:
        """Search for theme-related keywords to detect emerging topics.

        Strips any cashtags and caps results at 10 to conserve rate limit.
        """
        # Strip $ from any ticker-style keywords
        clean_keywords = [_strip_cashtag(kw) for kw in keywords[:3]]  # Max 3 terms to keep query short
        query = " OR ".join(f'"{kw}"' if " " in kw else kw for kw in clean_keywords)
        query += " lang:en"
        return self.search_recent(query, max_results=max_results)
