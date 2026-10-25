"""Ingestion pipeline: PDF file -> page text -> chunks -> embeddings -> document_chunks rows."""

import asyncio
import logging
import uuid
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import DocumentChunk, IngestionStatus, SourceDocument
from app.embeddings import get_embedder
from app.sources.chunking import PageText, chunk_pages, clean_page_text, remove_repeated_lines
from app.sources.storage import absolute_path

logger = logging.getLogger(__name__)

# Below this much text per page on average, the PDF is almost certainly scanned images.
MIN_CHARS_PER_PAGE = 50


class IngestionError(Exception):
    """A problem with the file itself. The message is shown to the user."""


def extract_pages(path: Path) -> list[PageText]:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise IngestionError("This PDF is password-protected. Upload an unlocked copy.")
        raw_pages = remove_repeated_lines([page.extract_text() or "" for page in reader.pages])
        return [
            PageText(page_number=i + 1, text=clean_page_text(raw))
            for i, raw in enumerate(raw_pages)
        ]
    except PdfReadError as exc:
        raise IngestionError(f"This file couldn't be read as a PDF ({exc}).") from exc


async def ingest_source(session: AsyncSession, source_id: uuid.UUID) -> None:
    """Extract, chunk, and store one source. Safe to run again on the same source:
    old chunks are replaced, never duplicated."""
    source = await session.get(SourceDocument, source_id)
    if source is None:
        logger.warning("Source %s no longer exists; skipping ingestion", source_id)
        return
    if source.file_path is None:
        logger.warning("Source %s has no file to ingest; skipping", source_id)
        return

    source.status = IngestionStatus.PROCESSING
    source.error = None
    await session.commit()

    settings = get_settings()
    try:
        # PDF parsing is CPU-bound and synchronous; run it in a thread so the
        # event loop isn't blocked.
        pages = await asyncio.to_thread(extract_pages, absolute_path(source.file_path))
        total_chars = sum(len(p.text) for p in pages)
        if not pages or total_chars < MIN_CHARS_PER_PAGE * len(pages):
            raise IngestionError(
                "No readable text found. The PDF may be scanned images; OCR isn't supported yet."
            )

        chunks = chunk_pages(
            pages,
            size=settings.chunk_size,
            overlap=settings.chunk_overlap,
            min_size=settings.chunk_min_size,
            min_prose_ratio=settings.chunk_min_prose_ratio,
        )

        # Embedding is the slow, CPU-heavy step (~0.1 s per chunk); run it in a thread.
        embedder = get_embedder()
        vectors = await asyncio.to_thread(embedder.embed_documents, [c.text for c in chunks])

        await session.execute(delete(DocumentChunk).where(DocumentChunk.source_id == source.id))
        session.add_all(
            DocumentChunk(
                source_id=source.id,
                chunk_index=c.index,
                page_number=c.page_number,
                text=c.text,
                embedding=vector,
            )
            for c, vector in zip(chunks, vectors, strict=True)
        )
        source.status = IngestionStatus.READY
        source.meta = {
            **source.meta,
            "page_count": len(pages),
            "chunk_count": len(chunks),
            "empty_pages": [p.page_number for p in pages if not p.text],
            "chunking": {
                "size": settings.chunk_size,
                "overlap": settings.chunk_overlap,
                "min_size": settings.chunk_min_size,
                "min_prose_ratio": settings.chunk_min_prose_ratio,
            },
            "embedding_model": embedder.name,
        }
        await session.commit()
        logger.info("Ingested source %s: %d pages, %d chunks", source.id, len(pages), len(chunks))
    except IngestionError as exc:
        await _mark_failed(session, source_id, str(exc))
    except Exception:
        logger.exception("Unexpected error ingesting source %s", source_id)
        await _mark_failed(session, source_id, "Unexpected error while processing this file.")
        raise


async def _mark_failed(session: AsyncSession, source_id: uuid.UUID, message: str) -> None:
    await session.rollback()
    source = await session.get(SourceDocument, source_id)
    if source is not None:
        source.status = IngestionStatus.FAILED
        source.error = message
        await session.commit()
