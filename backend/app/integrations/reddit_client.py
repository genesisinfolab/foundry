"""Reddit API Client — subreddit scanning for stock/theme mentions

Reddit requires a descriptive user-agent string: "Platform:AppID:Version (by u/Username)"
Using just the client_id as user-agent causes 403s.
"""
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
        # Reddit requires a proper user-agent: "Platform:AppID:Version (by u/Username)"
        user_agent = s.reddit_user_agent
        if not user_agent or len(user_agent) < 20 or ":" not in user_agent:
            user_agent = "script:NewmanTradingBot:1.0 (by u/newman_trading_bot)"
        self.reddit = praw.Reddit(
            client_id=s.reddit_client_id,
            client_secret=s.reddit_client_secret,
            user_agent=user_agent,
        )

    def get_hot_tickers(self, subreddit: str = "pennystocks", limit: int = 50) -> list[dict]:
        """Extract most-mentioned tickers from hot posts, including post text for sentiment."""
        ticker_pattern = re.compile(r'\$([A-Z]{1,5})\b')
        ticker_data: dict[str, dict] = {}

        try:
            sub = self.reddit.subreddit(subreddit)
            for post in sub.hot(limit=limit):
                text = f"{post.title} {post.selftext}"
                tickers = ticker_pattern.findall(text)
                for t in tickers:
                    if len(t) >= 2:  # Skip single-letter matches
                        if t not in ticker_data:
                            ticker_data[t] = {"mentions": 0, "posts": []}
                        ticker_data[t]["mentions"] += 1
                        ticker_data[t]["posts"].append({
                            "text": post.title[:200],
                            "score": post.score,
                        })
        except Exception as e:
            logger.warning(f"Reddit scan failed for r/{subreddit}: {e}")
            return []

        # Sort by mentions
        sorted_tickers = sorted(ticker_data.items(), key=lambda x: x[1]["mentions"], reverse=True)
        return [
            {
                "symbol": sym,
                "mentions": data["mentions"],
                "subreddit": subreddit,
                "posts": data["posts"][:5],  # Pass top 5 posts to sentiment analyzer
            }
            for sym, data in sorted_tickers[:20]
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
        """Get top mentioned tickers across all tracked subreddits, with post text for sentiment."""
        all_ticker_data: dict[str, dict] = {}

        for sub_name in STOCK_SUBREDDITS:
            tickers = self.get_hot_tickers(sub_name, limit=25)
            for t in tickers:
                sym = t["symbol"]
                if sym not in all_ticker_data:
                    all_ticker_data[sym] = {"total_mentions": 0, "posts": []}
                all_ticker_data[sym]["total_mentions"] += t["mentions"]
                all_ticker_data[sym]["posts"].extend(t.get("posts", []))

        sorted_tickers = sorted(
            all_ticker_data.items(),
            key=lambda x: x[1]["total_mentions"],
            reverse=True
        )
        return [
            {
                "symbol": sym,
                "total_mentions": data["total_mentions"],
                "posts": data["posts"][:10],
            }
            for sym, data in sorted_tickers[:30]
        ]
