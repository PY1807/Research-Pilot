import uuid

import pytest

from app.db.models import ResearchProject, SourceDocument, SourceType, User
from app.sources.ingestion import ingest_source
from tests.pdfs import make_pdf


async def _project(client, title="Search test") -> str:
    response = await client.post("/api/projects/", json={"title": title, "question": "Q?"})
    return response.json()["id"]


async def _ingested_source(client, session, project_id: str, pages: list[str], title: str) -> str:
    upload = await client.post(
        f"/api/projects/{project_id}/sources/",
        files={"file": (f"{title}.pdf", make_pdf(pages), "application/pdf")},
        data={"title": title},
    )
    source_id = upload.json()["id"]
    await ingest_source(session, uuid.UUID(source_id))
    return source_id


@pytest.fixture
async def searchable_project(client, session) -> dict:
    project_id = await _project(client)
    rag = await _ingested_source(
        client,
        session,
        project_id,
        [
            "Introduction. This paper studies document classification.",
            "Retrieval augmented generation fetches relevant passages from an index "
            "before the model answers, which keeps answers grounded in sources.",
        ],
        "RAG paper",
    )
    cooking = await _ingested_source(
        client,
        session,
        project_id,
        ["Bread baking needs flour, water, yeast and salt. Knead the dough well."],
        "Cooking notes",
    )
    return {"project_id": project_id, "rag": rag, "cooking": cooking}


async def test_search_ranks_the_relevant_passage_first(client, searchable_project):
    project_id = searchable_project["project_id"]

    response = await client.get(
        f"/api/projects/{project_id}/search/", params={"q": "retrieval augmented generation"}
    )

    assert response.status_code == 200
    results = response.json()
    top = results[0]
    assert top["source_id"] == searchable_project["rag"]
    assert top["source_title"] == "RAG paper"
    assert top["page_number"] == 2
    assert "Retrieval augmented generation" in top["text"]
    assert [r["score"] for r in results] == sorted((r["score"] for r in results), reverse=True)


async def test_search_respects_k(client, searchable_project):
    project_id = searchable_project["project_id"]

    response = await client.get(
        f"/api/projects/{project_id}/search/", params={"q": "paper", "k": 1}
    )

    assert len(response.json()) == 1


async def test_search_only_returns_chunks_from_the_requested_project(
    client, session, searchable_project
):
    other_project = await _project(client, "Other project")
    await _ingested_source(
        client,
        session,
        other_project,
        ["Retrieval augmented generation retrieval augmented generation."],
        "Other RAG",
    )

    results = (
        await client.get(
            f"/api/projects/{searchable_project['project_id']}/search/",
            params={"q": "retrieval augmented generation", "k": 20},
        )
    ).json()

    assert {r["source_title"] for r in results} <= {"RAG paper", "Cooking notes"}


async def test_search_validates_input(client, searchable_project):
    project_id = searchable_project["project_id"]

    empty = await client.get(f"/api/projects/{project_id}/search/", params={"q": ""})
    too_many = await client.get(f"/api/projects/{project_id}/search/", params={"q": "x", "k": 99})

    assert empty.status_code == 422
    assert too_many.status_code == 422


async def test_source_file_is_served_inline(client, searchable_project):
    response = await client.get(f"/api/sources/{searchable_project['rag']}/file/")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content.startswith(b"%PDF-")


async def test_other_users_project_cannot_be_searched_or_downloaded(client, session):
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
        file_path="uploads/nowhere.pdf",
    )
    session.add(source)
    await session.commit()

    search = await client.get(f"/api/projects/{project.id}/search/", params={"q": "secret"})
    download = await client.get(f"/api/sources/{source.id}/file/")

    assert search.status_code == 404
    assert download.status_code == 404


async def test_keyword_search_matches_stemmed_words(client, searchable_project):
    # "retrieving" and "Retrieval" share the stem 'retriev'; "fetched" matches "fetches".
    response = await client.get(
        f"/api/projects/{searchable_project['project_id']}/search/",
        params={"q": "retrieving fetched", "mode": "keyword"},
    )

    results = response.json()
    assert results[0]["source_title"] == "RAG paper"
    assert results[0]["keyword_rank"] == 1
    assert results[0]["semantic_rank"] is None


async def test_keyword_search_with_no_matching_words_returns_nothing(client, searchable_project):
    response = await client.get(
        f"/api/projects/{searchable_project['project_id']}/search/",
        params={"q": "xylophone", "mode": "keyword"},
    )

    assert response.json() == []


async def test_hybrid_results_report_ranks_from_both_methods(client, searchable_project):
    response = await client.get(
        f"/api/projects/{searchable_project['project_id']}/search/",
        params={"q": "retrieval augmented generation", "mode": "hybrid"},
    )

    top = response.json()[0]
    assert top["source_title"] == "RAG paper"
    assert top["semantic_rank"] == 1
    assert top["keyword_rank"] == 1


async def test_unknown_search_mode_is_rejected(client, searchable_project):
    response = await client.get(
        f"/api/projects/{searchable_project['project_id']}/search/",
        params={"q": "x", "mode": "magic"},
    )

    assert response.status_code == 422
