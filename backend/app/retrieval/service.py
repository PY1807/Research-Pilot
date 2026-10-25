"""Retrieval: find the chunks most relevant to a question. No HTTP here, so the same
functions serve the API, the evaluation harness (M3), and agent tools (M6).

Three modes:
- semantic: embedding similarity (meaning), via pgvector's HNSW index
- keyword:  Postgres full-text search (stemmed words), via a GIN index
- hybrid:   both lists merged with Reciprocal Rank Fusion
"""

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import DocumentChunk, IngestionStatus, SourceDocument
from app.embeddings import get_embedder

SearchMode = Literal["hybrid", "semantic", "keyword"]

# How many candidates each method contributes before fusion. Fusing deeper lists lets a
# chunk ranked e.g. 30th by meaning but 2nd by keywords still reach the top.
FUSION_CANDIDATES = 50
# RRF constant from Cormack et al. (2009). Larger = flatter: one #1 rank matters less.
RRF_K = 60


@dataclass(frozen=True)
class SearchResult:
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    page_number: int | None
    text: str
    # Meaning depends on the mode: cosine similarity (semantic), ts_rank_cd (keyword),
    # or RRF score (hybrid). Only compare scores within one mode.
    score: float
    semantic_rank: int | None = None  # 1-based position in the semantic list, if present
    keyword_rank: int | None = None  # 1-based position in the keyword list, if present


def _ready_chunks_in_project(project_id: uuid.UUID):
    return (
        select(DocumentChunk, SourceDocument.title)
        .join(SourceDocument, SourceDocument.id == DocumentChunk.source_id)
        .where(
            SourceDocument.project_id == project_id,
            SourceDocument.status == IngestionStatus.READY,
        )
    )


def _result(chunk: DocumentChunk, title: str, score: float, **ranks) -> SearchResult:
    return SearchResult(
        chunk_id=chunk.id,
        source_id=chunk.source_id,
        source_title=title,
        page_number=chunk.page_number,
        text=chunk.text,
        score=round(float(score), 4),
        **ranks,
    )


async def semantic_search(
    session: AsyncSession, project_id: uuid.UUID, query: str, k: int = 5
) -> list[SearchResult]:
    """Chunks whose embeddings point closest to the query's embedding."""
    query_vector = await asyncio.to_thread(get_embedder().embed_query, query)
    distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")

    # The HNSW index finds nearest neighbours across ALL projects, then the WHERE clause
    # drops other projects' chunks, which can leave fewer than k results. Iterative scan
    # (pgvector 0.8) keeps walking the graph until k rows survive the filter.
    await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))

    rows = await session.execute(
        _ready_chunks_in_project(project_id)
        .add_columns(distance)
        .where(DocumentChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(k)
    )
    return [
        _result(chunk, title, 1 - dist, semantic_rank=i)
        for i, (chunk, title, dist) in enumerate(rows, start=1)
    ]


def _any_word_tsquery(query: str):
    """Match chunks containing ANY of the query's words (OR), not all of them (AND).

    plainto_tsquery stems the words and drops stopwords but joins them with AND:
    'self-rout' & 'decid' & 'rag' & 'long' & 'context'. A natural question rarely has
    every word in one chunk, so we swap & for |. Ranking then rewards chunks that
    contain more of the words, closer together.
    """
    and_query = cast(func.plainto_tsquery("english", query), Text)
    return func.to_tsquery("english", func.replace(and_query, " & ", " | "))


async def keyword_search(
    session: AsyncSession, project_id: uuid.UUID, query: str, k: int = 5
) -> list[SearchResult]:
    """Chunks sharing stemmed words with the query, ranked by ts_rank_cd."""
    tsquery = _any_word_tsquery(query)
    # ts_rank_cd ("cover density") rewards query words that appear close together.
    # Normalization 1 divides by 1 + log(document length), so long chunks don't win
    # just by containing more words.
    rank = func.ts_rank_cd(DocumentChunk.search_vector, tsquery, 1).label("rank")
    rows = await session.execute(
        _ready_chunks_in_project(project_id)
        .add_columns(rank)
        .where(DocumentChunk.search_vector.op("@@")(tsquery))
        .order_by(rank.desc(), DocumentChunk.id)
        .limit(k)
    )
    return [
        _result(chunk, title, score, keyword_rank=i)
        for i, (chunk, title, score) in enumerate(rows, start=1)
    ]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[uuid.UUID]],
    k: int = RRF_K,
    weights: Sequence[float] | None = None,
) -> list[tuple[uuid.UUID, float]]:
    """Merge ranked lists using only positions: score = sum of weight / (k + rank).

    Scores from different methods aren't comparable (cosine ~0.8 vs ts_rank ~0.1), so
    RRF ignores them. An item ranked well by several lists rises to the top; an item
    found by only one list still counts. `weights` lets one list count more (weighted
    RRF); by default every list counts equally.
    """
    weights = weights or [1.0] * len(rankings)
    scores: dict[uuid.UUID, float] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


async def hybrid_search(
    session: AsyncSession,
    project_id: uuid.UUID,
    query: str,
    k: int = 5,
    keyword_weight: float | None = None,
) -> list[SearchResult]:
    """Semantic and keyword results merged with (weighted) Reciprocal Rank Fusion."""
    if keyword_weight is None:
        keyword_weight = get_settings().hybrid_keyword_weight
    semantic = await semantic_search(session, project_id, query, FUSION_CANDIDATES)
    keyword = await keyword_search(session, project_id, query, FUSION_CANDIDATES)

    by_id = {r.chunk_id: r for r in keyword}
    by_id.update({r.chunk_id: r for r in semantic})
    semantic_rank = {r.chunk_id: r.semantic_rank for r in semantic}
    keyword_rank = {r.chunk_id: r.keyword_rank for r in keyword}

    fused = reciprocal_rank_fusion(
        [[r.chunk_id for r in semantic], [r.chunk_id for r in keyword]],
        weights=[1.0, keyword_weight],
    )
    return [
        replace(
            by_id[chunk_id],
            score=round(score, 5),
            semantic_rank=semantic_rank.get(chunk_id),
            keyword_rank=keyword_rank.get(chunk_id),
        )
        for chunk_id, score in fused[:k]
    ]


SEARCH_FUNCTIONS = {
    "hybrid": hybrid_search,
    "semantic": semantic_search,
    "keyword": keyword_search,
}


async def search(
    session: AsyncSession,
    project_id: uuid.UUID,
    query: str,
    k: int = 5,
    mode: SearchMode = "hybrid",
) -> list[SearchResult]:
    return await SEARCH_FUNCTIONS[mode](session, project_id, query, k)
