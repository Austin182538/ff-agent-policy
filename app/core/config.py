from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Application settings
    app_name: str = "NFL Analytics API"
    debug: bool = True
    secret_key: str = "your-secret-key-change-in-production"
    
    # Database settings - Using SQLite for easy setup
    database_url: str = "sqlite:///./nfl_analytics.db"
    
    # Redis settings
    redis_url: str = "redis://localhost:6379"
    
    # CORS settings
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # API Keys (you'll need to obtain these)
    espn_api_key: str = ""
    nfl_api_key: str = ""

    # Vegas odds provider (https://the-odds-api.com) - free tier: 500 credits/month
    odds_api_key: str = ""
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"

    # FantasyPros news/injuries (optional, not wired up yet)
    fantasypros_api_key: str = ""

    # BettingPros API (undocumented public API behind www.bettingpros.com).
    # Carries season-long player prop O/U lines (incl. RB receiving yards and
    # reception totals, which fantasypoints.com does not) as a consensus of
    # the major books. Requires the site's x-api-key plus the browser Origin/
    # Referer headers (see app/integrations/bettingpros_client.py).
    bettingpros_api_key: str = ""
    bettingpros_base_url: str = "https://api.bettingpros.com/v3"
    
    # Celery settings
    celery_broker_url: str = "redis://localhost:6379"
    celery_result_backend: str = "redis://localhost:6379"
    
    # Data fetching settings
    data_fetch_interval_hours: int = 24
    max_seasons_to_fetch: int = 10
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env


# Create settings instance
settings = Settings() 