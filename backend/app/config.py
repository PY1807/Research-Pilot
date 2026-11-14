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

    # Reranking (M5): a cross-encoder re-scores hybrid search's top candidates.
    # "fastembed" runs the real model locally; "overlap" is a fast fake for tests.
    reranker_provider: str = "fastembed"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    reranker_batch_size: int = 16
    # How many hybrid results the cross-encoder reads. More = better recall, slower.
    rerank_candidates: int = 30

    # LLMs (M4). Providers are tried in the order listed; ones without an API key are
    # skipped. Answers prefer Gemini; the citation judge prefers a *different* model, so
    # the eval isn't a model grading its own answers. "fake" is the scripted test double.
    llm_answer_providers: str = "gemini,grok,groq"
    llm_judge_providers: str = "grok,groq,gemini"
    llm_timeout_seconds: float = 60.0

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    # xAI Grok (OpenAI-compatible). Paid per token; no standing free tier as of 2026-11.
    grok_api_key: str = ""
    grok_base_url: str = "https://api.x.ai/v1"
    grok_model: str = "grok-3-mini"
    # Groq (with a q): hosts open models (Llama etc.) on a free tier, OpenAI-compatible.
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    # USD per million tokens, as {"model": [input_price, output_price]}. Models missing
    # here (free tiers) are costed at 0; tokens are always counted either way.
    llm_prices_per_million: dict[str, tuple[float, float]] = {}

    # Cited answers (M4): how many passages the LLM sees per question.
    answer_top_k: int = 8
    # Retrieval for answers. Reranking won M5's experiment D by a wide margin, and an
    # answer already waits seconds for the LLM, so its extra latency matters less here.
    answer_retrieval_mode: str = "rerank"

    # Until auth lands in M8, every request acts as this single seeded user.
    dev_user_email: str = "dev@researchpilot.local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
