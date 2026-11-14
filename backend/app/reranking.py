"""Rerank search results with a cross-encoder. Like `embeddings.py`, the rest of the app
only sees the `Reranker` interface, so the model can change without touching search code.

Embedding search encodes the question and each passage *separately* and compares the two
vectors: fast enough for the whole corpus, but the model never sees them side by side.
A cross-encoder reads question and passage *together* in one pass and outputs a single
relevance score. Much more precise, much slower, so it only re-scores the top candidates
that hybrid search already found.
"""

import re
from functools import lru_cache
from typing import Protocol

from app.config import get_settings


class Reranker(Protocol):
    name: str

    def score(self, query: str, passages: list[str]) -> list[float]:
        """One relevance score per passage, higher = more relevant. Only the order
        matters; the scale depends on the model."""
        ...


class FastEmbedReranker:
    """A cross-encoder run locally through ONNX Runtime (CPU, no PyTorch), via FastEmbed."""

    def __init__(self, model_name: str, cache_dir: str, batch_size: int) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder  # heavy import

        self.name = model_name
        self._batch_size = batch_size
        self._model = TextCrossEncoder(model_name, cache_dir=cache_dir)

    def score(self, query: str, passages: list[str]) -> list[float]:
        return [float(s) for s in self._model.rerank(query, passages, batch_size=self._batch_size)]


class OverlapReranker:
    """Test stand-in: scores a passage by the share of the query's words it contains.
    Instant and deterministic; knows nothing about meaning."""

    name = "overlap-test-reranker"

    @staticmethod
    def _words(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def score(self, query: str, passages: list[str]) -> list[float]:
        query_words = self._words(query) or {""}
        return [len(query_words & self._words(p)) / len(query_words) for p in passages]


@lru_cache
def get_reranker() -> Reranker:
    """One reranker per process; loading the model takes a few seconds."""
    settings = get_settings()
    if settings.reranker_provider == "overlap":
        return OverlapReranker()
    if settings.reranker_provider == "fastembed":
        return FastEmbedReranker(
            settings.reranker_model, settings.embedding_cache_dir, settings.reranker_batch_size
        )
    raise ValueError(f"Unknown reranker provider: {settings.reranker_provider}")
