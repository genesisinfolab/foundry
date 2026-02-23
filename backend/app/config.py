"""Application configuration loaded from .env"""
from pydantic_settings import BaseSettings
from functools import lru_cache
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

    # App
    log_level: str = "INFO"
    database_url: str = "sqlite:///./newman_trading.db"

    # Newman Strategy Parameters
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
    stop_loss_pct: float = -0.005
    profit_take_tiers: list[float] = [0.15, 0.30, 0.45]
    max_pyramid_levels: int = 4

    model_config = {"env_file": os.path.join(os.path.dirname(__file__), "../../.env")}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
