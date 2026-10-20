from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # the backend/ folder


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(BASE_DIR / 'fund_tracker.db').as_posix()}"
    secret_key: str = Field(min_length=32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(60, gt=0)
    frontend_origin: str = "http://localhost:5173"
    default_monthly_contribution: int = Field(3000, gt=0)


settings = Settings()
