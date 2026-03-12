"""Base strategy interface for Foundry trading system.

All trading strategies must implement this interface. The strategy layer is
responsible for defining screening criteria, signal sources, position sizing,
and risk parameters. Execution infrastructure (Alpaca, DB, notifications) is
shared across strategies.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScreeningCriteria:
    """Parameters that define which securities to consider."""
    sectors: list[str] = field(default_factory=list)
    min_price: float = 0.0
    max_price: float | None = None  # None = no upper limit
    min_avg_volume: int = 0
    max_float: int | None = None    # None = no float cap
    additional_filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionSizing:
    """How the strategy sizes positions."""
    starter_usd: float = 2500.0
    max_single_position_pct: float = 0.35
    max_theme_exposure_pct: float = 0.60
    conviction_based: bool = False   # If True, size varies by conviction score


@dataclass
class RiskParameters:
    """Stop-loss and profit-taking rules."""
    stop_loss_pct: float = -0.05
    profit_take_tiers: list[float] = field(default_factory=lambda: [0.15, 0.30, 0.45])
    max_pyramid_levels: int = 4
    stopped_out_cooldown_hours: float = 24.0
    # If True, exit is thesis-driven rather than mechanical stop
    thesis_driven_exit: bool = False


@dataclass
class SignalSource:
    """A data source that feeds the strategy's signal detection."""
    name: str
    source_type: str   # "news", "13f", "etf_holdings", "social", "youtube", "manual"
    url: str | None = None
    weight: float = 1.0
    contrarian: bool = False  # If True, fade this source rather than follow it


class BaseStrategy(ABC):
    """Abstract base for all Foundry trading strategies.

    Subclasses define WHAT to trade and WHY. The scheduler, executor, and
    risk manager define HOW — those components are shared infrastructure.
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique slug: 'newman', 'golden', etc."""
        ...

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Human-readable name."""
        ...

    @abstractmethod
    def get_screening_criteria(self) -> ScreeningCriteria:
        """Securities universe and hard filters."""
        ...

    @abstractmethod
    def get_position_sizing(self) -> PositionSizing:
        """How to size new positions."""
        ...

    @abstractmethod
    def get_risk_parameters(self) -> RiskParameters:
        """Stop-loss and exit rules."""
        ...

    @abstractmethod
    def get_signal_sources(self) -> list[SignalSource]:
        """Ordered list of signal sources with weights."""
        ...

    @abstractmethod
    def get_entry_criteria(self) -> dict[str, Any]:
        """Strategy-specific entry conditions beyond basic screening."""
        ...

    @abstractmethod
    def get_exit_criteria(self) -> dict[str, Any]:
        """Strategy-specific exit conditions beyond mechanical stops."""
        ...

    @abstractmethod
    def get_persona_prompt(self) -> str:
        """Claude system prompt fragment for this strategy's AI analysis layer."""
        ...

    def describe(self) -> dict[str, Any]:
        """Serializable description of this strategy — used by API and logs."""
        sc = self.get_screening_criteria()
        ps = self.get_position_sizing()
        rp = self.get_risk_parameters()
        return {
            "strategy_id":   self.strategy_id,
            "strategy_name": self.strategy_name,
            "screening": {
                "sectors":          sc.sectors,
                "min_price":        sc.min_price,
                "max_price":        sc.max_price,
                "min_avg_volume":   sc.min_avg_volume,
                "max_float":        sc.max_float,
            },
            "position_sizing": {
                "starter_usd":              ps.starter_usd,
                "max_single_position_pct":  ps.max_single_position_pct,
                "conviction_based":         ps.conviction_based,
            },
            "risk": {
                "stop_loss_pct":        rp.stop_loss_pct,
                "profit_take_tiers":    rp.profit_take_tiers,
                "max_pyramid_levels":   rp.max_pyramid_levels,
                "thesis_driven_exit":   rp.thesis_driven_exit,
            },
            "signal_sources": [
                {"name": s.name, "type": s.source_type, "weight": s.weight, "contrarian": s.contrarian}
                for s in self.get_signal_sources()
            ],
        }
