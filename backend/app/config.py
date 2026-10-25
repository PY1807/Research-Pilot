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
    # Drop chunks that are almost all numbers (flattened tables, chart axes). 0.2 keeps
    # number-heavy prose such as abstracts that list model names and scores.
    chunk_min_prose_ratio: float = 0.2

    # Embeddings. "fastembed" runs the real model locally; "hash" is a fast fake for tests.
    # Changing the model's vector size needs a migration (document_chunks.embedding).
    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 32
    embedding_cache_dir: str = ".cache/fastembed"

    # Hybrid search: how much the keyword list counts relative to the semantic list in
    # Reciprocal Rank Fusion (1.0 = equal). Chosen on the benchmark; see DECISIONS.md.
    hybrid_keyword_weight: float = 1.0

    # Until auth lands in M8, every request acts as this single seeded user.
    dev_user_email: str = "dev@researchpilot.local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
