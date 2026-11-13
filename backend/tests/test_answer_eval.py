import json
import uuid
from types import SimpleNamespace

import pytest

from app.evaluation.answer_eval import _evaluate_question, load_questions
from app.evaluation.answer_metrics import aggregate, question_metrics
from app.llm.base import LLMError
from app.llm.providers import FakeProvider
from tests.test_search_api import _ingested_source, _project

RELEVANT = {("RAG paper", 2)}


def test_a_grounded_answer_scores_full_marks():
    scores = question_metrics(
        expected_answerable=True,
        answered=True,
        claim_citations=[["S1"], ["S1", "S2"]],
        dropped_citations=0,
        cited_units=[("RAG paper", 2), ("RAG paper", 2)],
        relevant=RELEVANT,
        support_verdicts=["supported", "supported"],
        correctness="correct",
    )
    assert scores == {
        "abstention_correct": 1.0,
        "citation_validity": 1.0,
        "cited_claim_rate": 1.0,
        "cited_page_precision": 1.0,
        "support_rate": 1.0,
        "support_or_partial": 1.0,
        "correctness": 1.0,
    }


def test_invented_citations_unlabelled_pages_and_weak_support_lower_the_scores():
    scores = question_metrics(
        expected_answerable=True,
        answered=True,
        claim_citations=[["S1"], []],
        dropped_citations=1,
        cited_units=[("RAG paper", 2), ("Other paper", 9)],
        relevant=RELEVANT,
        support_verdicts=["partial", "unsupported"],
        correctness="partial",
    )
    assert scores["citation_validity"] == 0.5
    assert scores["cited_claim_rate"] == 0.5
    assert scores["cited_page_precision"] == 0.5
    assert scores["support_rate"] == 0.0
    assert scores["support_or_partial"] == 0.5
    assert scores["correctness"] == 0.5


def test_abstaining_on_an_unanswerable_question_is_correct_and_nothing_else_is_scored():
    scores = question_metrics(
        expected_answerable=False,
        answered=False,
        claim_citations=[],
        dropped_citations=0,
        cited_units=[],
        relevant=set(),
    )
    assert scores == {"abstention_correct": 1.0}


def test_aggregate_only_averages_questions_that_have_the_metric():
    agg = aggregate([{"abstention_correct": 1.0, "support_rate": 0.5}, {"abstention_correct": 0.0}])
    assert agg["abstention_correct"] == {"mean": 0.5, "n": 2}
    assert agg["support_rate"] == {"mean": 0.5, "n": 1}
    assert "correctness" not in agg


def test_smoke_file_is_converted_to_the_benchmark_shape(tmp_path):
    path = tmp_path / "smoke.json"
    path.write_text(
        json.dumps({"questions": [{"id": "q1", "question": "Q?", "source": "s", "pages": [3]}]})
    )
    _, questions = load_questions(path)
    assert questions[0]["relevant"] == [{"source": "s", "pages": [3]}]
    assert questions[0]["type"] == "fact"


@pytest.fixture
async def project_id(client, session) -> uuid.UUID:
    project_id = await _project(client, "Answer eval test")
    await _ingested_source(
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
    return uuid.UUID(project_id)


ARGS = SimpleNamespace(k=2, mode="hybrid")
QUESTION = {
    "id": "f99",
    "type": "fact",
    "question": "How does retrieval augmented generation work?",
    "relevant": [{"source": "RAG paper", "pages": [2]}],
}


def _answer_citing(label: str) -> str:
    return json.dumps(
        {"answerable": True, "claims": [{"text": "It retrieves first.", "citations": [label]}]}
    )


async def test_evaluate_question_answers_judges_and_keeps_text_out_of_the_record(
    session, project_id
):
    # S1 is the top passage; with the hash embedder that's the page-2 RAG passage.
    answer_llm = FakeProvider([_answer_citing("S1")], name="gemini")
    judge = FakeProvider(
        [
            json.dumps(
                {
                    "claims": [{"index": 1, "verdict": "supported", "reason": "stated"}],
                    "correctness": "correct",
                }
            )
        ],
        name="grok",
    )

    record, sheet = await _evaluate_question(session, project_id, QUESTION, answer_llm, judge, ARGS)

    assert record["scores"]["support_rate"] == 1.0
    assert record["scores"]["correctness"] == 1.0
    assert record["scores"]["cited_page_precision"] == 1.0
    assert record["cited"] == ["RAG paper p2"]
    assert record["judge_llm"] == "grok/fake-model"
    # The judge saw the cited passage and the labelled reference page.
    judge_prompt = judge.requests[0].prompt
    assert '<claim index="1">It retrieves first.</claim>' in judge_prompt
    assert '<reference source="RAG paper" page="2">' in judge_prompt
    # Results JSON is committed to git, so it must not quote the corpus.
    assert "fetches relevant passages" not in json.dumps(record)
    # The local spot-check sheet does quote it, so a human can verify.
    assert "fetches relevant passages" in sheet["claims"][0]["cited"][0][2]


async def test_a_judge_failure_keeps_the_answer_metrics(session, project_id):
    class BrokenJudge:
        name, model = "grok", "m"

        async def generate(self, request):
            raise LLMError("HTTP 400: bad model")

    answer_llm = FakeProvider([_answer_citing("S1")])

    record, _ = await _evaluate_question(
        session, project_id, QUESTION, answer_llm, BrokenJudge(), ARGS
    )

    assert record["judge_error"].startswith("HTTP 400")
    assert record["scores"]["citation_validity"] == 1.0
    assert "support_rate" not in record["scores"]


async def test_unanswerable_questions_skip_the_judge(session, project_id):
    judge = FakeProvider([])
    answer_llm = FakeProvider([json.dumps({"answerable": False, "missing_information": "n/a"})])
    question = {**QUESTION, "type": "unanswerable", "relevant": []}

    record, _ = await _evaluate_question(session, project_id, question, answer_llm, judge, ARGS)

    assert record["scores"] == {"abstention_correct": 1.0}
    assert judge.requests == []
