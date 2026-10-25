"""Queue every uploaded source for ingestion again, e.g. after changing the chunking code
or chunk settings. Safe because ingestion replaces a source's old chunks.

Run with: python -m app.scripts.reingest
"""

import asyncio

from sqlalchemy import select

from app.db.models import SourceDocument
from app.db.session import SessionLocal, engine
from app.sources.tasks import ingest_source_task


async def main() -> None:
    async with SessionLocal() as session:
        ids = (
            await session.scalars(
                select(SourceDocument.id).where(SourceDocument.file_path.is_not(None))
            )
        ).all()
    await engine.dispose()
    for source_id in ids:
        ingest_source_task.delay(str(source_id))
    print(f"Queued {len(ids)} sources for re-ingestion.")


if __name__ == "__main__":
    asyncio.run(main())
