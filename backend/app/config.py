"""Application configuration loaded from .env"""
from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache
import logging
import os


class Settings(BaseSettings):
    # Alpaca
    alpaca_api_key_id: str = ""
    alpaca_api_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets/v2"
    alpaca_paper: bool = True

    # Finnhub
    finnhub_api_key: str = ""

    # Twitter
    twitter_bearer_token: str = ""
    twitter_api_key: str = ""
    twitter_api_secret_key: str = ""
    twitter_access_token: str = ""
    twitter_access_token_secret: str = ""

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "NewmanTrader/1.0"

    # Alpha Vantage
    alpha_vantage_api_key: str = ""

    # Perigon
    perigon_api_key: str = ""

    # Seeking Alpha (RapidAPI)
    seeking_alpha_token: str = ""

    # Anthropic (Claude gate)
    anthropic_api_key: str = ""

    # Optional API key for mutating endpoints (override, pipeline).
    # Leave empty to keep unauthenticated (dev mode).  Set in .env for production.
    override_api_key: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwks_url: str = ""  # Auth → Settings → JWKS URL  (ES256 — preferred)
    supabase_jwt_secret: str = ""  # Legacy HS256 fallback — leave blank if using JWKS

    # Operational mode — "paper", "live", or "paused"
    trading_mode: str = "paper"

    # Notifications
    whatsapp_number: str = ""
    ultramsg_instance_id: str = ""
    ultramsg_token: str = ""
    callmebot_api_key: str = ""

    # App
    log_level: str = "INFO"
    database_url: str = "sqlite:///./newman_trading.db"

    # Scheduler — set False locally so only Fly.io runs the trading engine.
    # Both instances share the same Alpaca account; only one should place orders.
    enable_scheduler: bool = True

    # Multi-tenancy (single-tenant today — owner_id maps to Supabase user ID in future).
    # All DB rows are stamped with this value; switching to JWT sub is a 1-day job later.
    owner_id: str = "default"

    # Strategy Parameters (will move to per-tenant config table when multi-tenancy ships)
    theme_news_weight: float = 0.4
    theme_social_weight: float = 0.3
    theme_etf_weight: float = 0.3
    max_float: int = 200_000_000
    min_price: float = 0.50
    min_avg_volume: int = 100_000
    volume_surge_multiplier: float = 2.5
    starter_position_usd: float = 2500.0
    max_single_position_pct: float = 0.35
    max_theme_exposure_pct: float = 0.60
    stop_loss_pct: float = -0.08  # Test A: was -0.05 (wider leash for penny stock noise)
    profit_take_tiers: list[float] = [0.10, 0.25, 0.50]  # Test A: was [0.15, 0.30, 0.45]
    max_pyramid_levels: int = 4
    stopped_out_cooldown_hours: float = 24.0  # Hours to block re-entry after a stop-out
    active_strategies: str = "newman"  # Comma-separated strategy IDs: newman,golden

    @model_validator(mode="after")
    def _warn_missing_critical_vars(self) -> "Settings":
        _cfg_logger = logging.getLogger(__name__)
        if not self.alpaca_api_key_id:
            _cfg_logger.warning("ALPACA_API_KEY_ID is not set — Alpaca integration will fail")
        if not self.alpaca_api_secret_key:
            _cfg_logger.warning("ALPACA_SECRET_KEY is not set — Alpaca integration will fail")
        if not self.whatsapp_number:
            _cfg_logger.warning("WHATSAPP_NUMBER is not set — trade notifications are disabled")
        return self

    model_config = {"env_file": os.path.join(os.path.dirname(__file__), "../../.env")}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
