"""
Social Sentiment Analyzer — Goes beyond counting mentions to analyze
what people are actually saying about stocks/themes.
"""
import logging
import re
from textblob import TextBlob
from collections import defaultdict

logger = logging.getLogger(__name__)

# Bullish/bearish signal words specific to stock trading
BULLISH_SIGNALS = [
    "moon", "rocket", "buying", "loaded", "calls", "bullish", "breakout",
    "squeeze", "undervalued", "accumulating", "diamond hands", "long",
    "catalyst", "dd", "due diligence", "partnership", "approval",
    "revenue beat", "earnings beat", "upgrade", "price target raised",
]

BEARISH_SIGNALS = [
    "puts", "shorting", "bearish", "dump", "dilution", "offering",
    "overvalued", "scam", "fraud", "warning", "downgrade", "sell",
    "bag holding", "dead cat", "bankruptcy", "sec investigation",
]


class SocialSentimentAnalyzer:
    def analyze_posts(self, posts: list[dict]) -> dict:
        """
        Analyze a collection of social media posts for trading sentiment.
        Returns aggregated sentiment with breakdown.
        """
        if not posts:
            return {"score": 0.0, "bullish_count": 0, "bearish_count": 0, "neutral_count": 0}

        results = []
        for post in posts:
            text = post.get("text", "") or post.get("title", "") or post.get("selftext", "")
            if not text:
                continue
            result = self._analyze_single(text, post)
            results.append(result)

        if not results:
            return {"score": 0.0, "bullish_count": 0, "bearish_count": 0, "neutral_count": 0}

        bullish = [r for r in results if r["sentiment"] == "bullish"]
        bearish = [r for r in results if r["sentiment"] == "bearish"]
        neutral = [r for r in results if r["sentiment"] == "neutral"]

        # Weight by engagement (likes, upvotes, etc.)
        total_weight = sum(r["weight"] for r in results)
        if total_weight == 0:
            total_weight = len(results)

        weighted_score = sum(r["score"] * r["weight"] for r in results) / total_weight

        return {
            "score": round(weighted_score, 3),  # -1 to 1
            "bullish_count": len(bullish),
            "bearish_count": len(bearish),
            "neutral_count": len(neutral),
            "total_posts": len(results),
            "bullish_pct": len(bullish) / len(results) if results else 0,
            "avg_engagement": total_weight / len(results) if results else 0,
            "top_bullish_signals": self._top_signals(bullish),
            "top_bearish_signals": self._top_signals(bearish),
        }

    def _analyze_single(self, text: str, post: dict) -> dict:
        """Analyze a single post"""
        text_lower = text.lower()

        # Count trading-specific signals
        bull_hits = sum(1 for s in BULLISH_SIGNALS if s in text_lower)
        bear_hits = sum(1 for s in BEARISH_SIGNALS if s in text_lower)

        # TextBlob general sentiment
        blob_sentiment = TextBlob(text).sentiment.polarity

        # Combined score: trading signals weighted more than general sentiment
        trading_score = (bull_hits - bear_hits) / max(bull_hits + bear_hits, 1)
        combined = trading_score * 0.6 + blob_sentiment * 0.4

        # Engagement weight (Reddit score, Twitter likes, etc.)
        weight = 1.0
        if "score" in post:  # Reddit
            weight = max(1.0, post["score"] ** 0.5)  # Square root to dampen outliers
        elif "public_metrics" in post:  # Twitter
            metrics = post["public_metrics"]
            weight = max(1.0, (metrics.get("like_count", 0) + metrics.get("retweet_count", 0) * 2) ** 0.5)

        if combined > 0.1:
            sentiment = "bullish"
        elif combined < -0.1:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        return {
            "score": combined,
            "sentiment": sentiment,
            "weight": weight,
            "bull_signals": bull_hits,
            "bear_signals": bear_hits,
            "matched_signals": [s for s in BULLISH_SIGNALS + BEARISH_SIGNALS if s in text_lower],
        }

    def _top_signals(self, posts: list[dict]) -> list[str]:
        """Get most common signal words from a set of posts"""
        all_signals = []
        for p in posts:
            all_signals.extend(p.get("matched_signals", []))
        from collections import Counter
        return [s for s, _ in Counter(all_signals).most_common(5)]

    def get_saturation_score(self, current_buzz: dict, historical_buzz: list[dict]) -> float:
        """
        Detect if a theme is becoming oversaturated (Newman's exit signal).
        Returns 0-1 where 1 = fully saturated (time to exit).
        """
        if not historical_buzz or not current_buzz:
            return 0.0

        current_posts = current_buzz.get("total_posts", 0)
        current_bullish = current_buzz.get("bullish_pct", 0)

        # Compare to historical average
        hist_posts = [h.get("total_posts", 0) for h in historical_buzz]
        hist_bullish = [h.get("bullish_pct", 0) for h in historical_buzz]

        avg_posts = sum(hist_posts) / len(hist_posts) if hist_posts else 1
        avg_bullish = sum(hist_bullish) / len(hist_bullish) if hist_bullish else 0.5

        # Saturation signals:
        # 1. Mention volume way above average (everyone's talking about it)
        volume_ratio = current_posts / avg_posts if avg_posts > 0 else 1
        # 2. Extremely high bullish % (euphoria = top signal)
        euphoria = current_bullish

        saturation = 0.0
        if volume_ratio > 5:  # 5x normal mentions
            saturation += 0.4
        elif volume_ratio > 3:
            saturation += 0.2

        if euphoria > 0.85:  # >85% bullish = danger
            saturation += 0.4
        elif euphoria > 0.75:
            saturation += 0.2

        # 3. Declining sentiment despite high volume (smart money leaving)
        if len(hist_bullish) >= 3:
            recent_trend = hist_bullish[-1] - hist_bullish[-3] if len(hist_bullish) >= 3 else 0
            if recent_trend < -0.1 and volume_ratio > 2:
                saturation += 0.2

        return min(saturation, 1.0)
