import uuid

from sqlalchemy import func, select

from app.db.models import (
    DocumentChunk,
    IngestionStatus,
    ResearchProject,
    SourceDocument,
    SourceType,
)
from app.sources.ingestion import ingest_source
from app.sources.storage import absolute_path, upload_relpath
from tests.pdfs import make_pdf, sentences


async def _source_with_file(session, user, content: bytes) -> SourceDocument:
    project = ResearchProject(user_id=user.id, title="Test", question="Q?")
    session.add(project)
    await session.flush()
    source = SourceDocument(
        id=uuid.uuid4(),
        user_id=user.id,
        project_id=project.id,
        title="Test PDF",
        source_type=SourceType.UPLOADED,
    )
    source.file_path = upload_relpath(user.id, source.id)
    path = absolute_path(source.file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    session.add(source)
    await session.commit()
    return source


async def _chunks(session, source_id):
    rows = await session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.source_id == source_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return rows.all()


async def test_ingestion_stores_chunks_with_correct_page_numbers(session, dev_user):
    pdf = make_pdf(
        [
            sentences("Opening", 20),
            sentences("Middle", 20) + " PAGE-TWO-MARKER appears here.",
            sentences("Closing", 20),
        ]
    )
    source = await _source_with_file(session, dev_user, pdf)

    await ingest_source(session, source.id)

    await session.refresh(source)
    assert source.status == IngestionStatus.READY
    assert source.meta["page_count"] == 3
    chunks = await _chunks(session, source.id)
    assert source.meta["chunk_count"] == len(chunks) > 3
    assert {c.page_number for c in chunks} == {1, 2, 3}
    marker_chunks = [c for c in chunks if "PAGE-TWO-MARKER" in c.text]
    assert marker_chunks and all(c.page_number == 2 for c in marker_chunks)


async def test_running_ingestion_twice_does_not_duplicate_chunks(session, dev_user):
    source = await _source_with_file(session, dev_user, make_pdf([sentences("Repeat", 30)]))

    await ingest_source(session, source.id)
    first = len(await _chunks(session, source.id))
    await ingest_source(session, source.id)

    total = await session.scalar(
        select(func.count()).select_from(DocumentChunk).where(DocumentChunk.source_id == source.id)
    )
    assert total == first


async def test_pdf_without_text_fails_with_clear_message(session, dev_user):
    source = await _source_with_file(session, dev_user, make_pdf(["", ""]))

    await ingest_source(session, source.id)

    await session.refresh(source)
    assert source.status == IngestionStatus.FAILED
    assert "No readable text" in source.error


async def test_corrupt_pdf_fails_with_clear_message(session, dev_user):
    source = await _source_with_file(session, dev_user, b"%PDF-1.7\nthis is not really a pdf")

    await ingest_source(session, source.id)

    await session.refresh(source)
    assert source.status == IngestionStatus.FAILED
    assert source.error


async def test_missing_source_is_ignored(session):
    await ingest_source(session, uuid.uuid4())  # must not raise
