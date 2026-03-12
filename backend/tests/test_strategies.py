"""Tests for strategy classes: base, newman, golden."""
import pytest
import sys
import os

# Ensure app is importable without full FastAPI startup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub out settings-dependent imports before loading strategy modules
import unittest.mock as mock

_settings_mock = mock.MagicMock()
_settings_mock.min_price = 0.50
_settings_mock.max_float = 200_000_000
_settings_mock.min_avg_volume = 100_000
_settings_mock.volume_surge_multiplier = 2.5
_settings_mock.starter_position_usd = 2500.0
_settings_mock.max_single_position_pct = 0.35
_settings_mock.max_theme_exposure_pct = 0.60
_settings_mock.stop_loss_pct = -0.005
_settings_mock.profit_take_tiers = [0.15, 0.30, 0.45]
_settings_mock.max_pyramid_levels = 4
_settings_mock.stopped_out_cooldown_hours = 24.0

with mock.patch("app.config.get_settings", return_value=_settings_mock):
    from app.strategies.base import (
        BaseStrategy, ScreeningCriteria, PositionSizing, RiskParameters, SignalSource
    )
    from app.strategies.newman import NewmanStrategy
    from app.strategies.golden import GoldenStrategy


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def newman():
    with mock.patch("app.config.get_settings", return_value=_settings_mock):
        return NewmanStrategy()


@pytest.fixture
def golden():
    return GoldenStrategy()


# ── Base dataclass sanity ─────────────────────────────────────────────────────

def test_screening_criteria_defaults():
    sc = ScreeningCriteria()
    assert sc.min_price == 0.0
    assert sc.max_price is None
    assert sc.sectors == []


def test_position_sizing_defaults():
    ps = PositionSizing()
    assert ps.starter_usd == 2500.0
    assert ps.conviction_based is False


def test_risk_parameters_defaults():
    rp = RiskParameters()
    assert rp.stop_loss_pct == -0.05
    assert rp.thesis_driven_exit is False
    assert len(rp.profit_take_tiers) == 3


def test_signal_source_fields():
    s = SignalSource(name="Test", source_type="news", weight=0.5)
    assert s.name == "Test"
    assert s.contrarian is False


# ── NewmanStrategy ────────────────────────────────────────────────────────────

def test_newman_instantiation(newman):
    assert newman.strategy_id == "newman"
    assert "Newman" in newman.strategy_name


def test_newman_screening_criteria(newman):
    with mock.patch("app.config.get_settings", return_value=_settings_mock):
        sc = newman.get_screening_criteria()
    assert sc.min_price == 0.50
    assert sc.max_price == 20.0
    assert "biotechnology" in sc.sectors
    assert sc.max_float == 200_000_000


def test_newman_position_sizing(newman):
    with mock.patch("app.config.get_settings", return_value=_settings_mock):
        ps = newman.get_position_sizing()
    assert ps.starter_usd == 2500.0
    assert ps.conviction_based is False


def test_newman_signal_sources(newman):
    sources = newman.get_signal_sources()
    assert len(sources) >= 3
    source_types = [s.source_type for s in sources]
    assert "news" in source_types


def test_newman_describe_shape(newman):
    with mock.patch("app.config.get_settings", return_value=_settings_mock):
        desc = newman.describe()
    assert desc["strategy_id"] == "newman"
    assert "screening" in desc
    assert "risk" in desc
    assert "signal_sources" in desc


def test_newman_entry_criteria(newman):
    with mock.patch("app.config.get_settings", return_value=_settings_mock):
        ec = newman.get_entry_criteria()
    assert ec["require_volume_surge"] is True
    assert ec["require_trendline_break"] is True


def test_newman_persona_prompt_non_empty(newman):
    assert len(newman.get_persona_prompt()) > 20


# ── GoldenStrategy ────────────────────────────────────────────────────────────

def test_golden_instantiation(golden):
    assert golden.strategy_id == "golden"
    assert "Golden" in golden.strategy_name


def test_golden_sectors_include_ai(golden):
    sc = golden.get_screening_criteria()
    assert "artificial_intelligence" in sc.sectors


def test_golden_no_float_ceiling(golden):
    sc = golden.get_screening_criteria()
    assert sc.max_float is None


def test_golden_conviction_tiers():
    g = GoldenStrategy()
    assert g.conviction_tier(0.80) == "high"
    assert g.conviction_tier(0.60) == "medium"
    assert g.conviction_tier(0.40) == "exploratory"
    assert g.conviction_tier(0.10) == "pass"


def test_golden_conviction_tier_boundaries():
    g = GoldenStrategy()
    assert g.conviction_tier(0.75) == "high"
    assert g.conviction_tier(0.749) == "medium"
    assert g.conviction_tier(0.50) == "medium"
    assert g.conviction_tier(0.499) == "exploratory"
    assert g.conviction_tier(0.30) == "exploratory"
    assert g.conviction_tier(0.299) == "pass"


def test_golden_position_sizing_guardrails():
    g = GoldenStrategy()
    portfolio = 100_000.0
    # High conviction: 20% of portfolio
    size = g.position_size_usd(0.80, portfolio)
    assert size == pytest.approx(20_000.0)
    # Medium: 10%
    size = g.position_size_usd(0.60, portfolio)
    assert size == pytest.approx(10_000.0)
    # Exploratory: 5%
    size = g.position_size_usd(0.40, portfolio)
    assert size == pytest.approx(5_000.0)
    # Pass: 0
    size = g.position_size_usd(0.10, portfolio)
    assert size == 0.0


def test_golden_position_sizing_max_cap():
    g = GoldenStrategy()
    # Even high conviction should never exceed 20% of portfolio
    portfolio = 50_000.0
    size = g.position_size_usd(0.80, portfolio)
    assert size <= portfolio * 0.20


def test_golden_price_filter_under_20():
    g = GoldenStrategy()
    assert g.price_passes(5.0, 0.10) is True
    assert g.price_passes(19.99, 0.10) is True
    assert g.price_passes(20.0, 0.10) is True


def test_golden_price_filter_override():
    g = GoldenStrategy()
    # $20-$100 requires high conviction
    assert g.price_passes(50.0, 0.80) is True
    assert g.price_passes(50.0, 0.60) is False
    assert g.price_passes(50.0, 0.74) is False


def test_golden_price_filter_hard_block():
    g = GoldenStrategy()
    # Over $100 always blocked regardless of conviction
    assert g.price_passes(101.0, 1.0) is False
    assert g.price_passes(500.0, 1.0) is False


def test_golden_wide_stop():
    g = GoldenStrategy()
    rp = g.get_risk_parameters()
    # Golden uses a wide -25% stop (thesis-driven, not stop-hunted)
    assert rp.stop_loss_pct == -0.25
    assert rp.thesis_driven_exit is True


def test_golden_conviction_based_sizing():
    g = GoldenStrategy()
    ps = g.get_position_sizing()
    assert ps.conviction_based is True


def test_golden_signal_sources_include_13f():
    g = GoldenStrategy()
    sources = g.get_signal_sources()
    types = [s.source_type for s in sources]
    assert "13f" in types


def test_golden_describe_shape():
    g = GoldenStrategy()
    desc = g.describe()
    assert desc["strategy_id"] == "golden"
    assert desc["risk"]["thesis_driven_exit"] is True


def test_golden_persona_prompt_non_empty():
    g = GoldenStrategy()
    assert len(g.get_persona_prompt()) > 20
    assert "Aschenbrenner" in g.get_persona_prompt()
