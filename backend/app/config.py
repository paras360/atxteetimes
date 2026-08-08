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
    # Route scraping through a proxy, e.g. http://user:pass@host:port. The
    # site's WAF bans datacenter IP ranges outright, so a residential/ISP proxy
    # is the only reliable egress from a cloud host.
    scraper_proxy: str = ""
    # Sticky-session port range. The provider binds one residential IP per port,
    # so changing port is how we change exit IP. Roughly half of residential IPs
    # are already WAF-blocked, so a blocked fetch hops ports rather than giving
    # up -- far better than pausing scanning.
    proxy_port_min: int = 10000
    proxy_port_max: int = 19999
    proxy_max_ip_attempts: int = 10
    # Separate, much smaller budget for unreachable exits. A timeout costs the
    # full read timeout in wall clock (a block fails instantly), so retrying as
    # many times as we retry blocks would exhaust the scan budget. We still
    # rotate away from the dead IP on the very first timeout.
    proxy_max_timeout_attempts: int = 3
    # Circuit breaker: only after every IP attempt fails does scanning back off.
    # With a working proxy this should effectively never trigger.
    block_backoff_start_minutes: int = 5
    block_backoff_max_minutes: int = 30
    # How long a bootstrapped CSRF token is reused before being refreshed. The
    # HTTP session outlives a single scan, so raising this cuts bootstrap
    # requests (and TLS handshakes) without risking many stale-token retries.
    csrf_token_ttl_minutes: int = 20
    # Off by default: the slim Docker image does not bundle Playwright/browsers.
    # Enable only if playwright + browsers are installed (see DEPLOY.md).
    # Note: useless against a hard IP ban - a real browser is blocked too.
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

    # Alerting
    # Ignore slots the site won't let you cart yet (dates beyond the booking
    # window). Otherwise every future date alerts as one huge unbookable batch
    # the moment it appears in results.
    require_bookable: bool = True
    # A date beyond the booking window returns a full page of uncartable rows,
    # so re-fetching it every 5 minutes is pure proxy bandwidth. Check those
    # dates this often instead; they revert to full-rate once bookable.
    unbookable_recheck_minutes: int = 30
    # Cap rows in one digest so a mass re-detection can't send a wall of slots.
    max_slots_per_email: int = 25
    # Warn once the scraper has been blocked this long, then repeat at most
    # every cooldown period, so an outage never goes unnoticed again.
    send_blocked_alerts: bool = True
    blocked_alert_after_minutes: int = 120
    blocked_alert_cooldown_hours: int = 12

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
