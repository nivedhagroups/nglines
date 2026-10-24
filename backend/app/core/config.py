from functools import lru_cache
import importlib

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+asyncpg://nivedha:nivedha@db:5432/nivedha"
    jwt_secret: str = Field(default="dev-only-change-this-secret", min_length=24)
    otp_hmac_secret: str = Field(default="dev-only-change-this-otp-secret", min_length=24)
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    otp_expiry_seconds: int = 300
    otp_max_attempts: int = 5
    otp_limit_count: int = 5
    otp_limit_window_seconds: int = 900
    otp_delivery: str = "console"
    push_delivery: str = "disabled"
    file_storage_root: str = "/data/files"
    public_api_base_url: str = "http://localhost:8000"
    allowed_origins: list[str] = ["http://localhost:8081"]

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.environment == "production":
            if self.jwt_secret == "dev-only-change-this-secret" or self.otp_hmac_secret == "dev-only-change-this-otp-secret":
                raise ValueError("Production requires unique JWT and OTP secrets")
            if self.otp_delivery == "console":
                raise ValueError("Console OTP delivery is not allowed in production")
            if self.push_delivery != "firebase":
                raise ValueError("Production requires Firebase push delivery")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()