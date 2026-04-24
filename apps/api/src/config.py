"""Configuration settings for PartyMap Bot."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # PartyMap API
    partymap_api_key: str = Field(alias="PARTYMAP_API_KEY")
    partymap_base_url: str = Field(
        default="https://api.partymap.com/api", alias="PARTYMAP_BASE_URL"
    )

    # Dev mode - use local server
    dev_mode: bool = Field(default=False, alias="DEV_MODE")
    dev_partymap_base_url: str = Field(
        default="http://host.docker.internal:5000/api", alias="DEV_PARTYMAP_BASE_URL"
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://partymap:partymap@localhost:5432/partymap_bot",
        alias="DATABASE_URL",
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # OpenRouter (DeepSeek)
    openrouter_api_key: str = Field(alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_model: str = Field(default="deepseek/deepseek-chat", alias="OPENROUTER_MODEL")

    # Exa Search
    exa_api_key: str = Field(alias="EXA_API_KEY")

    # CORS
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    # Goabase
    goabase_base_url: str = Field(
        default="https://www.goabase.net/api/party/", alias="GOABASE_BASE_URL"
    )

    # Discovery Schedule
    discovery_schedule_hour: int = Field(default=2, alias="DISCOVERY_SCHEDULE_HOUR")
    discovery_schedule_minute: int = Field(default=0, alias="DISCOVERY_SCHEDULE_MINUTE")
    discovery_queries_per_run: int = Field(default=3, alias="DISCOVERY_QUERIES_PER_RUN")

    # Cost Limits (in cents)
    max_cost_per_festival: int = Field(default=50, alias="MAX_COST_PER_FESTIVAL")  # $0.50
    max_cost_per_discovery: int = Field(default=200, alias="MAX_COST_PER_DISCOVERY")  # $2.00
    max_cost_per_day: int = Field(default=1000, alias="MAX_COST_PER_DAY")  # $10.00

    # Research
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    retry_delay_seconds: int = Field(default=300, alias="RETRY_DELAY_SECONDS")
    research_concurrency: int = Field(default=3, alias="RESEARCH_CONCURRENCY")

    # Retention
    failed_festival_retention_days: int = Field(default=30, alias="FAILED_FESTIVAL_RETENTION_DAYS")

    # Browser (Playwright)
    browser_headless: bool = Field(default=True, alias="BROWSER_HEADLESS")
    browser_timeout: int = Field(default=120000, alias="BROWSER_TIMEOUT")  # 2 minutes
    browser_slow_mo: int = Field(default=0, alias="BROWSER_SLOW_MO")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Development
    debug: bool = Field(default=False, alias="DEBUG")

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.debug

    @property
    def effective_partymap_base_url(self) -> str:
        """Get the effective PartyMap base URL."""
        if self.dev_mode:
            return self.dev_partymap_base_url
        return self.partymap_base_url

    @property
    def partymap_headers(self) -> dict:
        """Get headers for PartyMap API requests."""
        return {
            "X-API-Key": self.partymap_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
