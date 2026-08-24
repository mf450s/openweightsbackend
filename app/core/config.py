from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "openweightsbackend"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./openweights.db"
    auth_secret_key: SecretStr = SecretStr("change-me-in-production")
    auth_token_expire_minutes: int = 60 * 24 * 7
    refresh_token_expire_days: int = 30
    api_rate_limit_enabled: bool = True
    api_rate_limit_requests: int = Field(default=100, gt=0)
    api_rate_limit_window_seconds: int = Field(default=60, gt=0)
    api_rate_limit_trusted_proxies: str = ""
    api_rate_limit_proxy_header: str = "X-Forwarded-For"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
