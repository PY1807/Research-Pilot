import uuid

import pytest

from app.reranking import OverlapReranker
from app.retrieval.service import reranked_search
from tests.test_search_api import _ingested_source, _project


def test_overlap_reranker_scores_by_shared_words():
    scores = OverlapReranker().score(
        "long context models", ["Long context models work.", "Context matters.", "Bread."]
    )
    assert scores == [1.0, pytest.approx(1 / 3), 0.0]


@pytest.fixture
async def project_id(client, session) -> uuid.UUID:
    project_id = await _project(client, "Rerank test")
    # One page shares a single query word many times (favoured by keyword ranking);
    # another contains every query word once (what the reranker should favour).
    await _ingested_source(
        client,
        session,
        project_id,
        [
            "Retrieval retrieval retrieval retrieval retrieval retrieval systems.",
            "Position bias: long context models miss facts placed in the middle of retrieval "
            "inputs.",
        ],
        "Paper",
    )
    return uuid.UUID(project_id)


async def test_rerank_reorders_candidates_and_records_their_hybrid_rank(session, project_id):
    query = "position bias in long context models with retrieval"

    results = await reranked_search(session, project_id, query, k=2, candidates=10)

    assert len(results) == 2
    top = results[0]
    assert top.page_number == 2  # contains every query word
    assert top.hybrid_rank is not None
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
    assert sorted(r.hybrid_rank for r in results) == [1, 2]


async def test_rerank_pool_is_never_smaller_than_k(session, project_id):
    results = await reranked_search(session, project_id, "retrieval", k=2, candidates=1)
    assert len(results) == 2


async def test_rerank_on_an_empty_project_returns_nothing(client, session):
    empty = uuid.UUID(await _project(client, "Empty rerank"))
    assert await reranked_search(session, empty, "anything", k=5) == []


async def test_search_api_accepts_rerank_mode(client, session, project_id):
    response = await client.get(
        f"/api/projects/{project_id}/search/",
        params={"q": "position bias long context", "mode": "rerank", "k": 1},
    )

    assert response.status_code == 200
    [result] = response.json()
    assert result["page_number"] == 2
    assert result["hybrid_rank"] in (1, 2)
