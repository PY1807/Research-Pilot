"""Answer metrics (M4). Pure functions, no database or LLM, so they're easy to test.

Per question we measure four things, each only where it makes sense:
- abstention_correct: answered when it should, said "not enough evidence" when it should
- citation_validity:  share of citations that point at passages the model was shown
- cited_claim_rate:   share of claims that carry at least one valid citation
- cited_page_precision: share of cited passages on a labelled (source, page) unit
- support_rate / support_or_partial: the judge's verdict on claim vs cited passage
- correctness: the judge's verdict on the whole answer vs the labelled reference pages
"""

from collections.abc import Sequence
from statistics import mean

from app.evaluation.metrics import Unit

SUPPORT_VERDICTS = ("supported", "partial", "unsupported")
CORRECTNESS_SCORE = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}

# Report columns, in order. A question that lacks a metric (e.g. support on an abstention)
# is simply left out of that column's mean, and the count shows how many were scored.
ANSWER_COLUMNS = [
    "abstention_correct",
    "citation_validity",
    "cited_claim_rate",
    "cited_page_precision",
    "support_rate",
    "support_or_partial",
    "correctness",
]


def question_metrics(
    *,
    expected_answerable: bool,
    answered: bool,
    claim_citations: Sequence[Sequence[str]],
    dropped_citations: int,
    cited_units: Sequence[Unit | None],
    relevant: set[Unit],
    support_verdicts: Sequence[str] | None = None,
    correctness: str | None = None,
) -> dict[str, float]:
    """`claim_citations` holds each claim's valid citation labels; `cited_units` the
    (source, page) of each distinct cited passage."""
    scores: dict[str, float] = {"abstention_correct": float(answered == expected_answerable)}

    valid = sum(len(c) for c in claim_citations)
    if valid + dropped_citations:
        scores["citation_validity"] = valid / (valid + dropped_citations)
    if claim_citations:
        scores["cited_claim_rate"] = sum(bool(c) for c in claim_citations) / len(claim_citations)
    if expected_answerable and relevant and cited_units:
        hits = sum(unit is not None and unit in relevant for unit in cited_units)
        scores["cited_page_precision"] = hits / len(cited_units)
    if support_verdicts:
        n = len(support_verdicts)
        scores["support_rate"] = sum(v == "supported" for v in support_verdicts) / n
        scores["support_or_partial"] = (
            sum(v in ("supported", "partial") for v in support_verdicts) / n
        )
    if correctness in CORRECTNESS_SCORE:
        scores["correctness"] = CORRECTNESS_SCORE[correctness]
    return scores


def aggregate(per_question: Sequence[dict[str, float]]) -> dict[str, dict[str, float]]:
    """Mean of each metric over the questions that have it, plus how many that was."""
    out: dict[str, dict[str, float]] = {}
    for column in ANSWER_COLUMNS:
        values = [q[column] for q in per_question if column in q]
        if values:
            out[column] = {"mean": round(mean(values), 3), "n": len(values)}
    return out
