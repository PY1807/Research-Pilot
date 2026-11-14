import uuid

import pytest

from app.db.models import IngestionStatus, SourceDocument, SourceType
from app.evaluation.runner import run
from app.scripts import reingest
from tests.test_search_api import _project


@pytest.fixture
async def project_with_stuck_source(client, session, dev_user) -> tuple[str, uuid.UUID]:
    title = f"Guard test {uuid.uuid4().hex[:6]}"
    project_id = uuid.UUID(await _project(client, title))
    stuck = SourceDocument(
        user_id=dev_user.id,
        project_id=project_id,
        title="Stuck paper",
        source_type=SourceType.UPLOADED,
        file_path="stuck.pdf",
        status=IngestionStatus.PROCESSING,
    )
    session.add(stuck)
    await session.commit()
    return title, stuck.id


async def test_eval_refuses_a_partly_ingested_corpus(project_with_stuck_source):
    title, _ = project_with_stuck_source
    spec = {"version": "t", "questions": []}

    with pytest.raises(SystemExit, match="1 source\\(s\\) are not ready"):
        await run(spec, ["hybrid"], title)


async def test_reingest_stuck_requeues_only_unfinished_sources(
    project_with_stuck_source, monkeypatch
):
    _, stuck_id = project_with_stuck_source
    queued: list[str] = []
    monkeypatch.setattr(reingest.ingest_source_task, "delay", queued.append)

    await reingest.main(stuck_only=True)

    assert str(stuck_id) in queued
    # Ready sources (left over from other tests) are not queued again.
    from sqlalchemy import select

    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        ready = (
            await session.scalars(
                select(SourceDocument.id).where(SourceDocument.status == IngestionStatus.READY)
            )
        ).all()
    assert not {str(r) for r in ready} & set(queued)
