"""Retrieval: find the chunks most relevant to a question. No HTTP here, so the same
functions serve the API now and the evaluation harness (M3) and agent tools (M6) later."""

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk, IngestionStatus, SourceDocument
from app.embeddings import get_embedder


@dataclass(frozen=True)
class SearchResult:
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    page_number: int | None
    text: str
    score: float  # cosine similarity: 1 = same meaning, 0 = unrelated


async def semantic_search(
    session: AsyncSession, project_id: uuid.UUID, query: str, k: int = 5
) -> list[SearchResult]:
    """Embed the query and return the k chunks whose embeddings point closest to it."""
    query_vector = await asyncio.to_thread(get_embedder().embed_query, query)
    distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")

    # The HNSW index finds nearest neighbours across ALL projects, then the WHERE clause
    # drops other projects' chunks, which can leave fewer than k results. Iterative scan
    # (pgvector 0.8) keeps walking the graph until k rows survive the filter.
    await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))

    rows = await session.execute(
        select(DocumentChunk, SourceDocument.title, distance)
        .join(SourceDocument, SourceDocument.id == DocumentChunk.source_id)
        .where(
            SourceDocument.project_id == project_id,
            SourceDocument.status == IngestionStatus.READY,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(k)
    )
    return [
        SearchResult(
            chunk_id=chunk.id,
            source_id=chunk.source_id,
            source_title=title,
            page_number=chunk.page_number,
            text=chunk.text,
            score=round(1 - dist, 4),
        )
        for chunk, title, dist in rows
    ]
