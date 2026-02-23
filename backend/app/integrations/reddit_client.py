"""Reddit API Client — subreddit scanning for stock/theme mentions"""
import logging
import re
from collections import Counter
from typing import Optional
import praw
from app.config import get_settings

logger = logging.getLogger(__name__)

STOCK_SUBREDDITS = ["pennystocks", "wallstreetbets", "stocks", "smallstreetbets", "RobinHoodPennyStocks"]


class RedditClient:
    def __init__(self):
        s = get_settings()
        self.reddit = praw.Reddit(
            client_id=s.reddit_client_id,
            client_secret=s.reddit_client_secret,
            user_agent=s.reddit_user_agent,
        )

    def get_hot_tickers(self, subreddit: str = "pennystocks", limit: int = 50) -> list[dict]:
        """Extract most-mentioned tickers from hot posts"""
        ticker_pattern = re.compile(r'\$([A-Z]{1,5})\b')
        ticker_counts: Counter = Counter()

        try:
            sub = self.reddit.subreddit(subreddit)
            for post in sub.hot(limit=limit):
                text = f"{post.title} {post.selftext}"
                tickers = ticker_pattern.findall(text)
                for t in tickers:
                    if len(t) >= 2:  # Skip single-letter matches
                        ticker_counts[t] += 1
        except Exception as e:
            logger.warning(f"Reddit scan failed for r/{subreddit}: {e}")
            return []

        return [
            {"symbol": sym, "mentions": count, "subreddit": subreddit}
            for sym, count in ticker_counts.most_common(20)
        ]

    def get_theme_buzz(self, keywords: list[str], limit: int = 100) -> dict:
        """Search across stock subreddits for theme-related keywords"""
        total_posts = 0
        total_score = 0
        total_comments = 0

        for sub_name in STOCK_SUBREDDITS[:3]:  # Limit to top 3 to avoid rate limits
            try:
                sub = self.reddit.subreddit(sub_name)
                query = " OR ".join(keywords[:5])
                for post in sub.search(query, limit=limit, time_filter="week"):
                    total_posts += 1
                    total_score += post.score
                    total_comments += post.num_comments
            except Exception as e:
                logger.warning(f"Reddit theme search failed for r/{sub_name}: {e}")

        buzz = (total_posts * 0.4 + total_score * 0.003 + total_comments * 0.01)
        return {
            "keywords": keywords,
            "total_posts": total_posts,
            "total_score": total_score,
            "total_comments": total_comments,
            "buzz_score": min(buzz / 10, 1.0),  # Normalize to 0-1
        }

    def scan_all_subreddits(self) -> list[dict]:
        """Get top mentioned tickers across all tracked subreddits"""
        all_tickers: Counter = Counter()
        for sub_name in STOCK_SUBREDDITS:
            tickers = self.get_hot_tickers(sub_name, limit=25)
            for t in tickers:
                all_tickers[t["symbol"]] += t["mentions"]

        return [
            {"symbol": sym, "total_mentions": count}
            for sym, count in all_tickers.most_common(30)
        ]
