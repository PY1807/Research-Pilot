from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables (or a .env file in development)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = (
        "postgresql+asyncpg://researchpilot:researchpilot@localhost:5433/researchpilot"
    )

    redis_url: str = "redis://localhost:6379/0"

    # Uploaded files live here, outside the database. Relative paths resolve from the
    # backend folder, which the API and worker containers both mount.
    storage_dir: str = "storage"
    max_upload_bytes: int = 50 * 1024 * 1024

    # Chunking, measured in characters (~4 characters per token for English).
    # ~1200 characters (~300 tokens) fits comfortably inside common embedding models'
    # input limits. M3 compares sizes on the benchmark.
    chunk_size: int = 1200
    chunk_overlap: int = 200
    chunk_min_size: int = 200

    # Until auth lands in M8, every request acts as this single seeded user.
    dev_user_email: str = "dev@researchpilot.local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
