from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables (or a .env file in development)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = (
        "postgresql+asyncpg://researchpilot:researchpilot@localhost:5432/researchpilot"
    )

    # Until auth lands in M8, every request acts as this single seeded user.
    dev_user_email: str = "dev@researchpilot.local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
