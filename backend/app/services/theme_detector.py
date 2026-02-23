"""
Theme Detection Service — Step 1 of Newman Strategy

Scans multiple sources to identify emerging sectors/themes:
- News (Finnhub, Perigon) for keywords
- Social (Twitter, Reddit) for buzz
- ETF performance (via Alpaca) for sector rotation

Score = news * 0.4 + social * 0.3 + etf * 0.3
"""
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from textblob import TextBlob

from app.config import get_settings
from app.models.theme import Theme, ThemeSource, ThemeStatus
from app.models.alert import Alert
from app.integrations.finnhub_client import FinnhubClient
from app.integrations.twitter_client import TwitterClient
from app.integrations.reddit_client import RedditClient
from app.integrations.perigon_client import PerigonClient
from app.integrations.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)

# Keywords that signal potential themes (Newman's approach)
CATALYST_KEYWORDS = [
    "approval", "legalization", "breakthrough", "pilot program",
    "clinical trial", "disruptive", "mandate", "regulation",
    "merger", "acquisition", "partnership", "FDA", "patent",
    "contract", "award", "launch", "revolutionary",
]

# Specialized ETFs to track for sector rotation
SECTOR_ETFS = {
    "cannabis": ["MJ", "MSOS"],
    "3d_printing": ["PRNT"],
    "clean_energy": ["TAN", "ICLN", "QCLN"],
    "robotics_ai": ["ARKQ", "ROBO", "BOTZ"],
    "biotech": ["XBI", "IBB", "ARKG"],
    "semiconductors": ["SMH", "SOXX"],
    "cybersecurity": ["HACK", "CIBR", "BUG"],
    "space": ["UFO", "ARKX"],
    "genomics": ["ARKG"],
    "fintech": ["ARKF", "FINX"],
    "ev": ["DRIV", "LIT", "IDRV"],
    "quantum": ["QTUM"],
    "blockchain": ["BLOK"],
    "metals_mining": ["XME", "PICK"],
    "nuclear": ["NLR", "URA"],
}


class ThemeDetector:
    def __init__(self):
        self.finnhub = FinnhubClient()
        self.twitter = TwitterClient()
        self.reddit = RedditClient()
        self.perigon = PerigonClient()
        self.alpaca = AlpacaClient()
        self.settings = get_settings()

    def scan_all(self, db: Session) -> list[Theme]:
        """Run full theme detection scan across all sources"""
        logger.info("Starting theme detection scan...")
        theme_scores: dict[str, dict] = defaultdict(lambda: {
            "news_score": 0.0, "social_score": 0.0, "etf_score": 0.0,
            "keywords": [], "sources": [], "etfs": [],
        })

        # 1. Scan news for catalyst keywords
        self._scan_news(theme_scores)

        # 2. Scan social media
        self._scan_social(theme_scores)

        # 3. Scan ETF performance for sector rotation
        self._scan_etfs(theme_scores)

        # 4. Score and persist themes
        themes = self._score_and_persist(theme_scores, db)

        logger.info(f"Theme scan complete. Found {len(themes)} themes.")
        return themes

    def _scan_news(self, scores: dict):
        """Scan Finnhub + Perigon for theme-related news"""
        logger.info("Scanning news sources...")

        # Finnhub general market news
        try:
            news = self.finnhub.market_news()
            for article in news[:100]:
                headline = article.get("headline", "").lower()
                summary = article.get("summary", "").lower()
                text = f"{headline} {summary}"

                # Check for catalyst keywords
                matched_keywords = [kw for kw in CATALYST_KEYWORDS if kw.lower() in text]
                if matched_keywords:
                    # Use TextBlob for basic sentiment
                    sentiment = TextBlob(text).sentiment.polarity
                    # Derive theme name from the dominant keyword context
                    theme_name = self._extract_theme_name(text, matched_keywords)
                    if theme_name:
                        scores[theme_name]["news_score"] += (0.3 + abs(sentiment) * 0.2)
                        scores[theme_name]["keywords"].extend(matched_keywords)
                        scores[theme_name]["sources"].append({
                            "type": "news", "source": "finnhub",
                            "headline": article.get("headline"),
                            "url": article.get("url"),
                            "sentiment": sentiment,
                        })
        except Exception as e:
            logger.warning(f"Finnhub news scan failed: {e}")

        # Perigon news for each catalyst keyword
        for keyword in CATALYST_KEYWORDS[:5]:  # Limit API calls
            try:
                articles = self.perigon.search_news(keyword, days=7, size=10)
                for article in articles:
                    theme_name = self._extract_theme_name(
                        f"{article.get('title', '')} {article.get('description', '')}",
                        [keyword],
                    )
                    if theme_name:
                        scores[theme_name]["news_score"] += 0.2
                        scores[theme_name]["sources"].append({
                            "type": "news", "source": "perigon",
                            "headline": article.get("title"),
                            "url": article.get("url"),
                            "sentiment": article.get("sentiment", 0),
                        })
            except Exception as e:
                logger.warning(f"Perigon scan failed for '{keyword}': {e}")

    def _scan_social(self, scores: dict):
        """Scan Twitter + Reddit for trending themes"""
        logger.info("Scanning social media...")

        # Reddit: get trending tickers and look for theme clusters
        try:
            all_tickers = self.reddit.scan_all_subreddits()
            # Group mentions by potential themes
            for ticker_data in all_tickers[:15]:
                symbol = ticker_data["symbol"]
                mentions = ticker_data["total_mentions"]
                if mentions >= 3:  # Minimum mention threshold
                    # Use symbol as temporary theme identifier
                    scores[f"ticker_{symbol}"]["social_score"] += min(mentions / 20, 1.0)
                    scores[f"ticker_{symbol}"]["sources"].append({
                        "type": "reddit", "source": "reddit",
                        "headline": f"${symbol} mentioned {mentions} times across stock subreddits",
                        "sentiment": 0.5,  # Assume moderately positive if being discussed
                    })
        except Exception as e:
            logger.warning(f"Reddit scan failed: {e}")

        # Twitter: search for themes from SECTOR_ETFS
        for theme_name, etfs in list(SECTOR_ETFS.items())[:5]:  # Limit API calls
            try:
                keywords = [theme_name.replace("_", " "), f"${etfs[0]}"]
                tweets = self.twitter.search_theme_mentions(keywords, max_results=50)
                if len(tweets) > 10:
                    scores[theme_name]["social_score"] += min(len(tweets) / 50, 1.0)
                    scores[theme_name]["sources"].append({
                        "type": "twitter", "source": "twitter",
                        "headline": f"Found {len(tweets)} tweets about {theme_name}",
                        "sentiment": 0.3,
                    })
            except Exception as e:
                logger.warning(f"Twitter scan failed for {theme_name}: {e}")

    def _scan_etfs(self, scores: dict):
        """Scan ETF performance for sector rotation signals"""
        logger.info("Scanning ETF performance...")

        for theme_name, etf_symbols in SECTOR_ETFS.items():
            for etf in etf_symbols:
                try:
                    bars = self.alpaca.get_bars(etf, days=30)
                    if len(bars) < 5:
                        continue

                    # Calculate recent performance
                    recent_close = bars[-1]["close"]
                    week_ago = bars[-5]["close"] if len(bars) >= 5 else bars[0]["close"]
                    month_ago = bars[0]["close"]

                    week_return = (recent_close - week_ago) / week_ago
                    month_return = (recent_close - month_ago) / month_ago

                    # Volume analysis
                    recent_vol = sum(b["volume"] for b in bars[-5:]) / 5
                    avg_vol = sum(b["volume"] for b in bars) / len(bars)
                    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

                    # Score: strong recent performance + volume surge = hot sector
                    etf_score = 0.0
                    if week_return > 0.03:  # >3% weekly return
                        etf_score += 0.3
                    if month_return > 0.10:  # >10% monthly return
                        etf_score += 0.3
                    if vol_ratio > 1.5:  # Volume 50%+ above average
                        etf_score += 0.2

                    if etf_score > 0:
                        scores[theme_name]["etf_score"] = max(scores[theme_name]["etf_score"], etf_score)
                        scores[theme_name]["etfs"].append(etf)
                        scores[theme_name]["sources"].append({
                            "type": "etf", "source": etf,
                            "headline": f"{etf}: week={week_return:.1%} month={month_return:.1%} vol_ratio={vol_ratio:.1f}x",
                            "sentiment": week_return,
                        })
                except Exception as e:
                    logger.warning(f"ETF scan failed for {etf}: {e}")

    def _score_and_persist(self, theme_scores: dict, db: Session) -> list[Theme]:
        """Calculate composite scores and save to database"""
        s = self.settings
        themes = []

        for name, data in theme_scores.items():
            # Skip low-signal themes
            composite = (
                data["news_score"] * s.theme_news_weight
                + data["social_score"] * s.theme_social_weight
                + data["etf_score"] * s.theme_etf_weight
            )
            if composite < 0.1:
                continue

            # Determine status
            if composite > 0.6:
                status = ThemeStatus.HOT
            elif composite > 0.3:
                status = ThemeStatus.EMERGING
            else:
                status = ThemeStatus.COOLING

            # Upsert theme
            theme = db.query(Theme).filter(Theme.name == name).first()
            if theme:
                theme.score = composite
                theme.news_score = data["news_score"]
                theme.social_score = data["social_score"]
                theme.etf_score = data["etf_score"]
                theme.status = status
                theme.keywords = json.dumps(list(set(data["keywords"])))
                theme.related_etfs = json.dumps(data["etfs"])
                theme.updated_at = datetime.now(timezone.utc)
            else:
                theme = Theme(
                    name=name,
                    score=composite,
                    news_score=data["news_score"],
                    social_score=data["social_score"],
                    etf_score=data["etf_score"],
                    status=status,
                    keywords=json.dumps(list(set(data["keywords"]))),
                    related_etfs=json.dumps(data["etfs"]),
                )
                db.add(theme)

            # Add sources
            for src in data["sources"][:10]:  # Limit stored sources
                source = ThemeSource(
                    theme=theme,
                    source_type=src["type"],
                    source_name=src["source"],
                    headline=src.get("headline"),
                    url=src.get("url"),
                    sentiment=src.get("sentiment", 0),
                )
                db.add(source)

            # Create alert for hot themes
            if status == ThemeStatus.HOT:
                alert = Alert(
                    alert_type="theme_detected",
                    theme_name=name,
                    title=f"🔥 Hot Theme Detected: {name}",
                    message=f"Score: {composite:.2f} (news={data['news_score']:.2f}, social={data['social_score']:.2f}, etf={data['etf_score']:.2f})",
                    severity="action",
                )
                db.add(alert)

            themes.append(theme)

        db.commit()
        return themes

    def _extract_theme_name(self, text: str, keywords: list[str]) -> Optional[str]:
        """Extract a theme name from text context"""
        text_lower = text.lower()

        # Check against known sector themes
        for theme_name in SECTOR_ETFS:
            readable = theme_name.replace("_", " ")
            if readable in text_lower:
                return theme_name

        # Fallback: use the first matched keyword as theme identifier
        if keywords:
            return f"catalyst_{keywords[0].replace(' ', '_')}"

        return None
