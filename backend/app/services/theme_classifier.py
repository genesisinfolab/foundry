"""
Theme Classifier — Uses LLM or advanced NLP to classify whether a news cluster
represents a real investable theme vs noise.

Falls back to keyword matching if no LLM API is available.
"""
import logging
import re
from collections import Counter, defaultdict
from textblob import TextBlob

logger = logging.getLogger(__name__)

# Investable theme categories that Newman would care about
INVESTABLE_CATEGORIES = {
    "regulatory_catalyst": {
        "keywords": ["fda approval", "legalization", "regulation", "mandate", "legislation",
                     "executive order", "policy change", "deregulation", "ban lifted"],
        "weight": 1.0,  # Highest conviction — regulation moves sectors
    },
    "technology_breakthrough": {
        "keywords": ["breakthrough", "revolutionary", "first ever", "patent granted",
                     "clinical trial success", "phase 3", "novel", "disruptive"],
        "weight": 0.9,
    },
    "sector_momentum": {
        "keywords": ["sector rally", "industry boom", "demand surge", "shortage",
                     "supply chain", "record demand", "backlog"],
        "weight": 0.8,
    },
    "m_and_a": {
        "keywords": ["acquisition", "merger", "buyout", "takeover", "tender offer"],
        "weight": 0.7,
    },
    "government_spending": {
        "keywords": ["government contract", "defense spending", "infrastructure bill",
                     "stimulus", "subsidy", "grant awarded", "federal funding"],
        "weight": 0.8,
    },
    "consumer_trend": {
        "keywords": ["viral", "trending", "cult following", "sold out", "waitlist",
                     "record sales", "mainstream adoption"],
        "weight": 0.6,
    },
}

# Noise patterns to filter out
NOISE_PATTERNS = [
    r"building permit approval",
    r"board approv",
    r"shareholder approval",
    r"loan approval",
    r"insurance approval",
    r"planning approval",
]


class ThemeClassifier:
    def __init__(self):
        self.noise_patterns = [re.compile(p, re.IGNORECASE) for p in NOISE_PATTERNS]

    def classify_articles(self, articles: list[dict]) -> list[dict]:
        """
        Classify a batch of articles into investable theme categories.
        Returns enriched articles with category and confidence.
        """
        classified = []
        for article in articles:
            text = f"{article.get('title', '')} {article.get('description', '')}".lower()

            # Filter noise
            if self._is_noise(text):
                continue

            # Classify
            best_category = None
            best_score = 0.0

            for cat_name, cat_data in INVESTABLE_CATEGORIES.items():
                score = 0.0
                matched = []
                for kw in cat_data["keywords"]:
                    if kw in text:
                        score += cat_data["weight"]
                        matched.append(kw)

                if score > best_score:
                    best_score = score
                    best_category = cat_name

            if best_category and best_score > 0:
                # Add sentiment
                sentiment = TextBlob(text).sentiment
                article["category"] = best_category
                article["category_score"] = best_score
                article["sentiment_polarity"] = sentiment.polarity
                article["sentiment_subjectivity"] = sentiment.subjectivity
                classified.append(article)

        return classified

    def cluster_into_themes(self, classified_articles: list[dict]) -> list[dict]:
        """
        Group classified articles into distinct investable themes.
        Articles about the same sector/topic get merged.
        """
        # Group by category + extract sector keywords
        theme_clusters: dict[str, list] = defaultdict(list)

        for article in classified_articles:
            # Extract sector from text
            sector = self._extract_sector(article.get("title", "") + " " + article.get("description", ""))
            key = f"{article['category']}_{sector}" if sector else article["category"]
            theme_clusters[key].append(article)

        # Score each cluster
        themes = []
        for key, articles in theme_clusters.items():
            if len(articles) < 1:
                continue

            avg_sentiment = sum(a.get("sentiment_polarity", 0) for a in articles) / len(articles)
            total_score = sum(a.get("category_score", 0) for a in articles)

            themes.append({
                "name": key,
                "category": articles[0]["category"],
                "article_count": len(articles),
                "total_score": total_score,
                "avg_sentiment": avg_sentiment,
                "confidence": min(total_score / 3.0, 1.0),  # Normalize
                "sample_headlines": [a.get("title", "") for a in articles[:5]],
            })

        # Sort by confidence
        themes.sort(key=lambda t: t["confidence"], reverse=True)
        return themes

    def _is_noise(self, text: str) -> bool:
        """Check if text matches noise patterns (non-investable 'approval' etc.)"""
        for pattern in self.noise_patterns:
            if pattern.search(text):
                return True
        return False

    def _extract_sector(self, text: str) -> str:
        """Extract sector/industry from text"""
        text_lower = text.lower()
        sectors = {
            "cannabis": ["cannabis", "marijuana", "cbd", "thc", "weed"],
            "biotech": ["biotech", "pharmaceutical", "drug", "fda", "clinical trial", "gene therapy"],
            "ai": ["artificial intelligence", " ai ", "machine learning", "neural", "llm"],
            "semiconductor": ["semiconductor", "chip", "wafer", "foundry", "fab"],
            "ev": ["electric vehicle", " ev ", "battery", "lithium", "charging"],
            "solar": ["solar", "photovoltaic", "renewable energy", "clean energy"],
            "nuclear": ["nuclear", "uranium", "reactor", "fusion"],
            "space": ["space", "satellite", "rocket", "orbit", "aerospace"],
            "quantum": ["quantum", "qubit"],
            "cybersecurity": ["cybersecurity", "cyber", "ransomware", "data breach"],
            "robotics": ["robot", "automation", "drone"],
            "mining": ["mining", "rare earth", "lithium", "cobalt", "nickel"],
            "defense": ["defense", "military", "pentagon", "weapons"],
            "fintech": ["fintech", "blockchain", "crypto", "defi", "digital payment"],
        }
        for sector, keywords in sectors.items():
            for kw in keywords:
                if kw in text_lower:
                    return sector
        return "general"
