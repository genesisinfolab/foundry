"""
Golden Strategy — Chuck's personal generational-tech conviction thesis.

Thesis: Third ~80-year technology wave (AI, quantum, robotics, biotech).
Sources: Aschenbrenner Situational Awareness paper, ARK Invest, 13F filings.
Timing: Contrarian — buy corrections, not rallies.
Sizing: Concentrated conviction tiers (high 20%, medium 10%, exploratory 5%).
"""
from app.strategies.base import (
    BaseStrategy,
    ScreeningCriteria,
    PositionSizing,
    RiskParameters,
    SignalSource,
)


GOLDEN_SECTORS = [
    "artificial_intelligence",
    "quantum_computing",
    "robotics",
    "biotechnology",
    "clean_energy",
    "space",
    "semiconductors",
    "defense_tech",
]

# Situational Awareness LP Q4 2025 holdings (Aschenbrenner watchlist)
SITUATIONAL_AWARENESS_HOLDINGS = [
    "BE",    # Bloom Energy
    "CRWV",  # CoreWeave
    "LITE",  # Lumentum
    "CORZ",  # Core Scientific
    "IREN",  # Iris Energy
    "APLD",  # Applied Digital
    "SNDK",  # SanDisk
]

# ARK ETF tickers to cross-reference
ARK_ETFS = ["ARKK", "ARKQ", "ARKG", "ARKX", "ARKF", "ARKW"]


class GoldenStrategy(BaseStrategy):
    """
    Chuck's generational-tech conviction strategy.

    Entry logic differs from Newman in two key ways:
    1. Correction timing — prefers to enter during S&P drawdowns, not rallies.
       correction_score >= 40 unlocks entries; correction_score >= 70 is
       the ideal buy window (max conviction sizing).
    2. "A deal is a deal" price override — price under $20 is a heuristic
       screening filter, not a hard wall. If conviction is high and the
       thesis is intact, the scanner can override the price ceiling.
    """

    @property
    def strategy_id(self) -> str:
        return "golden"

    @property
    def strategy_name(self) -> str:
        return "Golden — Generational Tech Conviction"

    def get_screening_criteria(self) -> ScreeningCriteria:
        return ScreeningCriteria(
            sectors=GOLDEN_SECTORS,
            min_price=0.50,
            max_price=20.0,           # soft ceiling — "a deal is a deal" override allowed
            min_avg_volume=50_000,    # lower bar than Newman; smaller-cap tech OK
            max_float=None,           # no float ceiling — large caps OK if thesis fits
            additional_filters={
                "price_override_allowed": True,
                "require_sector_fit": True,
                "cross_reference_13f": True,
                "cross_reference_ark": True,
                "prefer_correction_entry": True,
                "min_correction_score": 30,   # correction_score 0-100 from market_sentiment
            },
        )

    def get_position_sizing(self) -> PositionSizing:
        return PositionSizing(
            starter_usd=2_500,
            max_single_position_pct=0.20,     # hard cap: 20% single position
            max_theme_exposure_pct=0.40,       # hard cap: 40% per sector
            conviction_based=True,
        )

    def get_risk_parameters(self) -> RiskParameters:
        return RiskParameters(
            stop_loss_pct=-0.25,               # wide stop — thesis-driven, not stop-hunted
            profit_take_tiers=[0.50, 1.00, 2.00, 5.00],  # 50%, 100%, 200%, 500%
            max_pyramid_levels=3,
            stopped_out_cooldown_hours=72,     # longer cooldown — let thesis breathe
            thesis_driven_exit=True,           # exit on thesis break, not price target
        )

    def get_signal_sources(self) -> list[SignalSource]:
        return [
            SignalSource(
                name="Situational Awareness LP (13F)",
                source_type="13f",
                url="https://www.sec.gov/cgi-bin/browse-edgar",
                weight=0.35,
                contrarian=False,
            ),
            SignalSource(
                name="ARK Invest Daily Holdings",
                source_type="etf",
                url="https://ark-funds.com/funds/",
                weight=0.25,
                contrarian=False,
            ),
            SignalSource(
                name="Market Correction Detector",
                source_type="market_sentiment",
                url="",
                weight=0.20,
                contrarian=True,   # high correction score = buy signal
            ),
            SignalSource(
                name="Finnhub Tech News",
                source_type="news",
                url="",
                weight=0.15,
                contrarian=False,
            ),
            SignalSource(
                name="Reddit r/singularity / r/MachineLearning",
                source_type="social",
                url="",
                weight=0.05,
                contrarian=False,
            ),
        ]

    def get_entry_criteria(self) -> dict:
        return {
            "require_sector_fit": True,
            "correction_score_min": 30,        # market must be at least mildly correcting
            "correction_score_ideal": 70,      # ideal entry window
            "price_max_soft": 20.0,            # soft ceiling — overridable
            "price_override_trigger": "high_conviction",
            "cross_reference_sources": ["13f", "ark"],
            "min_cross_reference_hits": 1,     # in at least one institutional source
            "conviction_tiers": {
                "high": {"min_score": 0.75, "position_pct": 0.20},
                "medium": {"min_score": 0.50, "position_pct": 0.10},
                "exploratory": {"min_score": 0.30, "position_pct": 0.05},
            },
            "drawdown_circuit_breaker": -0.25, # stop all new entries at -25% portfolio drawdown
        }

    def get_exit_criteria(self) -> dict:
        return {
            "thesis_break": True,              # primary exit: thesis no longer valid
            "information_parity": True,        # exit when market catches up (edge gone)
            "time_horizon_years": 5,
            "profit_tiers": [0.50, 1.00, 2.00, 5.00],
            "trailing_stop_after_pct": 1.00,   # trail stop after +100%
            "stop_loss_pct": -0.25,
        }

    def get_persona_prompt(self) -> str:
        return (
            "You are the Golden strategy engine — a high-conviction generational-tech investor "
            "modeled on Chuck's personal thesis from Aschenbrenner's Situational Awareness paper. "
            "You believe we are in the third ~80-year technology wave (AI, quantum, robotics, biotech) "
            "with asymmetric upside over a 5+ year horizon. "
            "You buy during corrections, not rallies. You concentrate in your highest-conviction ideas. "
            "Price is a screening heuristic, not a wall — 'a deal is a deal'. "
            "You cross-reference Situational Awareness LP 13F filings and ARK Invest holdings. "
            "You exit when the thesis breaks or when information parity is reached (market caught up). "
            "Analyze this candidate through that lens: sector fit, institutional signal overlap, "
            "correction timing, conviction tier, and thesis integrity."
        )

    def conviction_tier(self, score: float) -> str:
        """Map a 0.0-1.0 conviction score to a named tier."""
        if score >= 0.75:
            return "high"
        if score >= 0.50:
            return "medium"
        if score >= 0.30:
            return "exploratory"
        return "pass"

    def position_size_usd(self, conviction_score: float, portfolio_value: float) -> float:
        """
        Return the USD position size for a given conviction score and portfolio value.

        Hard guardrails:
          - max single position: 20% of portfolio
          - drawdown circuit breaker enforced by caller (golden_scanner)
        """
        tier = self.conviction_tier(conviction_score)
        tiers = self.get_entry_criteria()["conviction_tiers"]
        if tier == "pass":
            return 0.0
        pct = tiers[tier]["position_pct"]
        return min(portfolio_value * pct, portfolio_value * 0.20)

    def price_passes(self, price: float, conviction_score: float) -> bool:
        """
        Price filter with "a deal is a deal" override.

        Under $20 → always passes.
        $20-$100 → passes only with high conviction (>= 0.75).
        Over $100 → blocked (this is a small-cap / asymmetric-upside strategy).
        """
        if price <= 20.0:
            return True
        if price <= 100.0 and conviction_score >= 0.75:
            return True
        return False
