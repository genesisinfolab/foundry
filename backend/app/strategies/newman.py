"""Newman Strategy — penny-stock sector breakout system.

Jeffrey Newman persona. Focuses on small-cap sector momentum plays:
high float-adjusted volume surges, trendline resistance breaks, catalyst confirmation.
Time horizon: days to weeks. Entry: shotgun with pyramiding on confirmation.
"""
from app.strategies.base import (
    BaseStrategy, ScreeningCriteria, PositionSizing, RiskParameters, SignalSource
)
from app.config import get_settings


class NewmanStrategy(BaseStrategy):

    @property
    def strategy_id(self) -> str:
        return "newman"

    @property
    def strategy_name(self) -> str:
        return "Newman — Penny Stock Sector Breakout"

    def get_screening_criteria(self) -> ScreeningCriteria:
        s = get_settings()
        return ScreeningCriteria(
            sectors=[
                "biotechnology", "semiconductors", "clean_energy", "ai_software",
                "defense", "healthcare", "mining", "cannabis", "electric_vehicles",
            ],
            min_price=s.min_price,
            max_price=20.0,
            min_avg_volume=s.min_avg_volume,
            max_float=s.max_float,
            additional_filters={
                "volume_surge_multiplier": s.volume_surge_multiplier,
                "require_trendline_break": True,
                "require_sector_theme": True,
            },
        )

    def get_position_sizing(self) -> PositionSizing:
        s = get_settings()
        return PositionSizing(
            starter_usd=s.starter_position_usd,
            max_single_position_pct=s.max_single_position_pct,
            max_theme_exposure_pct=s.max_theme_exposure_pct,
            conviction_based=False,
        )

    def get_risk_parameters(self) -> RiskParameters:
        s = get_settings()
        return RiskParameters(
            stop_loss_pct=s.stop_loss_pct,
            profit_take_tiers=s.profit_take_tiers,
            max_pyramid_levels=s.max_pyramid_levels,
            stopped_out_cooldown_hours=s.stopped_out_cooldown_hours,
            thesis_driven_exit=False,
        )

    def get_signal_sources(self) -> list[SignalSource]:
        return [
            SignalSource("Finnhub News",     "news",         weight=0.4),
            SignalSource("Reddit Mentions",  "social",       weight=0.2),
            SignalSource("Twitter Mentions", "social",       weight=0.1),
            SignalSource("ETF Holdings",     "etf_holdings", weight=0.3),
        ]

    def get_entry_criteria(self) -> dict:
        return {
            "require_volume_surge": True,
            "volume_surge_multiplier": get_settings().volume_surge_multiplier,
            "require_trendline_break": True,
            "trendline_lookback_bars": 252,
            "min_conviction_corners": 2,  # chart + structure + sector + catalyst (min 2/4)
            "spy_bull_regime_gate": True,
        }

    def get_exit_criteria(self) -> dict:
        s = get_settings()
        return {
            "stop_loss_pct": s.stop_loss_pct,
            "profit_tiers": s.profit_take_tiers,
            "max_hold_days": 30,
            "trail_on_pyramid": True,
        }

    def get_persona_prompt(self) -> str:
        return (
            "You are Jeffrey Newman, a sharp penny stock trader focused on sector breakouts. "
            "Evaluate whether this stock shows the hallmarks of a legitimate momentum play: "
            "volume surge on a trendline break, a hot sector theme, and a clean share structure. "
            "Be skeptical of weak hands, hype without fundamentals, and crowded trades. "
            "Format your analysis in Jeffrey's direct, no-nonsense voice."
        )
