"""Turn text into vectors. The rest of the app only sees the `Embedder` interface, so the
model or provider can change without touching ingestion or search code."""

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

# Must match the vector column size in document_chunks (see the M2 migration).
EMBEDDING_DIM = 384


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """BAAI/bge-small-en-v1.5 run locally through ONNX Runtime (no PyTorch, CPU only).

    bge models are trained with a short instruction in front of search queries but not
    in front of passages; FastEmbed's `query_embed` adds it for us.
    """

    def __init__(self, model_name: str, cache_dir: str, batch_size: int) -> None:
        from fastembed import TextEmbedding  # heavy import; only load when used

        self.name = model_name
        self._batch_size = batch_size
        self._model = TextEmbedding(model_name, cache_dir=cache_dir)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts, batch_size=self._batch_size)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed([text]))).tolist()


class HashEmbedder:
    """Deterministic stand-in for tests: no model download, instant. Each word is hashed
    to a dimension, so texts sharing words get similar vectors. Keyword-level only;
    it has no idea that "car" and "vehicle" are related."""

    name = "hash-test-embedder"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * EMBEDDING_DIM
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.md5(word.encode()).digest()
            vec[int.from_bytes(digest[:4], "little") % EMBEDDING_DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@lru_cache
def get_embedder() -> Embedder:
    """One embedder per process. Loading the model takes seconds, so it's done once and
    reused by every request (API) or task (worker)."""
    settings = get_settings()
    if settings.embedding_provider == "hash":
        return HashEmbedder()
    if settings.embedding_provider == "fastembed":
        return FastEmbedEmbedder(
            settings.embedding_model, settings.embedding_cache_dir, settings.embedding_batch_size
        )
    raise ValueError(f"Unknown embedding provider: {settings.embedding_provider}")
