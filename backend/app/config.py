"""Application configuration"""
from functools import lru_cache
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    # App
    app_name: str = "ATX Tee Times Watcher"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./atxteetimes.db"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_expire_days: int = 30
    allow_signup: bool = True

    # Values considered unsafe for a deployed instance.
    INSECURE_SECRETS: ClassVar[set[str]] = {"", "change-me", "change-me-in-production"}

    @property
    def jwt_secret_is_insecure(self) -> bool:
        return self.jwt_secret.strip() in self.INSECURE_SECRETS

    # Email (Resend)
    resend_api_key: str = ""
    email_from: str = "alerts@stoutoilandgas.com"
    base_url: str = "http://localhost:8000"

    # CORS
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # WebTrac scraping
    webtrac_base_url: str = "https://txaustinweb.myvscloud.com/webtrac/web"
    request_timeout: int = 30      # per-request read timeout (seconds)
    connect_timeout: int = 10      # per-request connect timeout (seconds)
    # Hard ceiling on a single scan cycle. Once exceeded, the scan stops issuing
    # new fetches so a slow/throttled site can't hold the scan lock for many
    # minutes and starve every subsequent scheduled run.
    scan_budget_seconds: int = 240
    # Off by default: the slim Docker image does not bundle Playwright/browsers.
    # Enable only if playwright + browsers are installed (see DEPLOY.md).
    use_playwright_fallback: bool = False

    # Scheduling (America/Chicago)
    timezone: str = "America/Chicago"
    enable_scheduler: bool = True
    scan_interval_minutes: int = 5
    scan_start_weekday: int = 1   # Tuesday (Mon=0)
    scan_start_hour: int = 6      # 06:00
    scan_end_weekday: int = 6     # Sunday (inclusive)
    found_slot_retention_days: int = 10

    # Weekly "set up your watches" reminder (sent on scan_start_weekday).
    send_weekly_reminder: bool = True
    reminder_hour: int = 5        # 05:00, one hour before the scan window opens

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
