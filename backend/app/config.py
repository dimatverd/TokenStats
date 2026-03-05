"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./tokenstats.db"
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    FERNET_KEY: str = ""
    CORS_ORIGINS: list[str] = ["*"]

    # Polling intervals (seconds)
    POLLING_INTERVAL_RATE_LIMITS: int = 60
    POLLING_INTERVAL_USAGE_COSTS: int = 300

    # Cache TTL (seconds)
    CACHE_TTL_RATE_LIMITS: int = 60
    CACHE_TTL_USAGE: int = 300
    CACHE_TTL_COSTS: int = 300

    # APNs push notifications (all optional — notifications disabled when empty)
    APNS_TEAM_ID: str = ""
    APNS_KEY_ID: str = ""
    APNS_PRIVATE_KEY: str = ""
    APNS_USE_SANDBOX: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
