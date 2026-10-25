"""Celery tasks for sources. These run in the worker process, not the API."""

import asyncio
import uuid

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.sources.ingestion import ingest_source
from app.worker import celery_app


@celery_app.task(
    name="sources.ingest",
    # Retry only when the database is briefly unreachable. ingest_source replaces old
    # chunks, so running it again is safe.
    autoretry_for=(OperationalError, InterfaceError),
    retry_backoff=True,
    max_retries=3,
)
def ingest_source_task(source_id: str) -> None:
    asyncio.run(_run(uuid.UUID(source_id)))


async def _run(source_id: uuid.UUID) -> None:
    # Each task gets its own event loop (asyncio.run), and pooled connections can't be
    # shared across loops, so the worker uses a fresh unpooled engine per task.
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await ingest_source(session, source_id)
    finally:
        await engine.dispose()
