from functools import lru_cache
import importlib

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+asyncpg://nivedha:nivedha@db:5432/nivedha"
    jwt_secret: str = Field(default="dev-only-change-this-secret", min_length=24)
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    password_login_limit: int = 10
    password_login_window_seconds: int = 900
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Nivedha Groups"
    smtp_starttls: bool = True
    push_delivery: str = "disabled"
    file_storage_root: str = "backend/storage/files"
    public_api_base_url: str = "http://localhost:8000"
    allowed_origins: list[str] = ["http://localhost:8081"]

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.environment == "production":
            if self.jwt_secret == "dev-only-change-this-secret":
                raise ValueError("Production requires a unique JWT secret")
            if self.push_delivery != "firebase":
                raise ValueError("Production requires Firebase push delivery")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()