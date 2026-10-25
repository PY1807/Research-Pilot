import uuid

import pytest

from app.config import get_settings
from app.db.models import IngestionStatus, ResearchProject, SourceDocument, SourceType, User
from app.sources.ingestion import ingest_source
from app.sources.storage import absolute_path
from tests.pdfs import make_pdf, sentences


@pytest.fixture
async def project_id(client) -> str:
    response = await client.post(
        "/api/projects/", json={"title": "RAG vs long context", "question": "When does RAG win?"}
    )
    assert response.status_code == 201
    return response.json()["id"]


def _pdf_upload(content: bytes, name: str = "paper.pdf"):
    return {"file": (name, content, "application/pdf")}


async def test_upload_saves_file_and_queues_ingestion(client, session, project_id, queued_tasks):
    response = await client.post(
        f"/api/projects/{project_id}/sources/", files=_pdf_upload(make_pdf(["Hello world."]))
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["title"] == "paper"
    assert body["source_type"] == "uploaded"
    assert queued_tasks == [body["id"]]
    source = await session.get(SourceDocument, uuid.UUID(body["id"]))
    assert absolute_path(source.file_path).read_bytes().startswith(b"%PDF-")


async def test_status_and_chunks_after_ingestion(client, session, project_id):
    upload = await client.post(
        f"/api/projects/{project_id}/sources/",
        files=_pdf_upload(make_pdf([sentences("One", 10), sentences("Two", 10)])),
        data={"title": "Two page paper"},
    )
    source_id = upload.json()["id"]

    pending = await client.get(f"/api/sources/{source_id}/status/")
    assert pending.json()["status"] == "pending"

    await ingest_source(session, uuid.UUID(source_id))

    status = (await client.get(f"/api/sources/{source_id}/status/")).json()
    assert status["status"] == "ready"
    assert status["page_count"] == 2
    chunks = (await client.get(f"/api/sources/{source_id}/chunks/")).json()
    assert len(chunks) == status["chunk_count"]
    assert {c["page_number"] for c in chunks} == {1, 2}

    listed = (await client.get(f"/api/projects/{project_id}/sources/")).json()
    assert [s["title"] for s in listed] == ["Two page paper"]


async def test_non_pdf_upload_is_rejected(client, project_id):
    response = await client.post(
        f"/api/projects/{project_id}/sources/",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
    )

    assert response.status_code == 415


async def test_empty_upload_is_rejected(client, project_id):
    response = await client.post(f"/api/projects/{project_id}/sources/", files=_pdf_upload(b""))

    assert response.status_code == 400


async def test_oversized_upload_is_rejected(client, project_id, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100)

    response = await client.post(
        f"/api/projects/{project_id}/sources/", files=_pdf_upload(make_pdf([sentences("Big", 50)]))
    )

    assert response.status_code == 413


async def test_duplicate_upload_in_same_project_is_rejected(client, project_id):
    pdf = make_pdf(["Exactly the same file."])
    first = await client.post(f"/api/projects/{project_id}/sources/", files=_pdf_upload(pdf))

    second = await client.post(f"/api/projects/{project_id}/sources/", files=_pdf_upload(pdf))

    assert second.status_code == 409
    assert first.json()["id"] in second.json()["detail"]


async def test_other_users_project_and_source_are_not_visible(client, session):
    other = User(email=f"other-{uuid.uuid4()}@example.com")
    session.add(other)
    await session.flush()
    project = ResearchProject(user_id=other.id, title="Private", question="Secret?")
    session.add(project)
    await session.flush()
    source = SourceDocument(
        user_id=other.id,
        project_id=project.id,
        title="Private paper",
        source_type=SourceType.UPLOADED,
        status=IngestionStatus.READY,
    )
    session.add(source)
    await session.commit()

    assert (await client.get(f"/api/projects/{project.id}/")).status_code == 404
    upload = await client.post(
        f"/api/projects/{project.id}/sources/", files=_pdf_upload(make_pdf(["Hi."]))
    )
    assert upload.status_code == 404
    assert (await client.get(f"/api/sources/{source.id}/status/")).status_code == 404
    assert (await client.get(f"/api/sources/{source.id}/chunks/")).status_code == 404
