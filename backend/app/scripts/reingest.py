"""Queue every uploaded source for ingestion again, e.g. after changing the chunking code
or chunk settings. Safe because ingestion replaces a source's old chunks.

Run with: python -m app.scripts.reingest            (every source)
          python -m app.scripts.reingest --stuck    (only sources not finished)

--stuck recovers sources left "pending" or "processing" when a worker was killed
mid-job (e.g. restarted by a code change). Re-running a finished source is harmless.
"""

import asyncio
import sys

from sqlalchemy import select

from app.db.models import IngestionStatus, SourceDocument
from app.db.session import SessionLocal, engine
from app.sources.tasks import ingest_source_task


async def main(stuck_only: bool = False) -> None:
    query = select(SourceDocument.id).where(SourceDocument.file_path.is_not(None))
    if stuck_only:
        query = query.where(
            SourceDocument.status.in_([IngestionStatus.PENDING, IngestionStatus.PROCESSING])
        )
    async with SessionLocal() as session:
        ids = (await session.scalars(query)).all()
    await engine.dispose()
    for source_id in ids:
        ingest_source_task.delay(str(source_id))
    print(f"Queued {len(ids)} sources for re-ingestion.")


if __name__ == "__main__":
    asyncio.run(main(stuck_only="--stuck" in sys.argv))
