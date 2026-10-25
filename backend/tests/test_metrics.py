import pytest

from app.evaluation.metrics import (
    Retrieved,
    average,
    hit_at_k,
    page_recall_at_k,
    percentile,
    precision_at_k,
    reciprocal_rank,
    relevant_units,
    score_question,
    source_recall_at_k,
)

LABELS = [{"source": "paperA", "pages": [3, 4]}, {"source": "paperB", "pages": [7]}]
UNITS = relevant_units(LABELS)

RANKED = [
    Retrieved("paperC", 1),  # not relevant
    Retrieved("paperA", 3),  # relevant
    Retrieved("paperA", 9),  # right paper, wrong page: not relevant
    Retrieved("paperA", 3),  # same relevant page again (a second chunk)
    Retrieved("paperB", 7),  # relevant
]


def test_relevant_units_expands_pages():
    assert UNITS == {("paperA", 3), ("paperA", 4), ("paperB", 7)}


def test_hit_at_k():
    assert hit_at_k(RANKED, UNITS, 1) == 0.0
    assert hit_at_k(RANKED, UNITS, 2) == 1.0


def test_reciprocal_rank_uses_first_relevant_position():
    assert reciprocal_rank(RANKED, UNITS) == 0.5
    assert reciprocal_rank([Retrieved("paperC", 1)], UNITS) == 0.0


def test_precision_counts_relevant_chunks_in_top_k():
    assert precision_at_k(RANKED, UNITS, 5) == pytest.approx(3 / 5)
    assert precision_at_k(RANKED, UNITS, 2) == pytest.approx(1 / 2)


def test_page_recall_counts_distinct_units():
    # Found (A,3) and (B,7) out of 3 units; the duplicate (A,3) counts once.
    assert page_recall_at_k(RANKED, UNITS, 5) == pytest.approx(2 / 3)


def test_source_recall_counts_sources_covered():
    assert source_recall_at_k(RANKED, UNITS, 2) == pytest.approx(1 / 2)
    assert source_recall_at_k(RANKED, UNITS, 5) == 1.0


def test_results_without_page_are_never_relevant():
    assert hit_at_k([Retrieved("paperA", None)], UNITS, 1) == 0.0


def test_score_question_and_average():
    scores = score_question(RANKED, LABELS, ks=[5])
    assert scores["hit@5"] == 1.0
    assert scores["mrr@10"] == 0.5

    assert average([{"m": 1.0}, {"m": 0.0}, {"m": 0.5}]) == {"m": 0.5}
    assert average([]) == {}


def test_percentile_nearest_rank():
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert percentile(values, 50) == 50
    assert percentile(values, 95) == 100
    assert percentile([5], 95) == 5
