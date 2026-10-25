"""Retrieval metrics. Pure functions over ranked results and labels, with no database.

Relevance is labelled at the level of (source, page): a retrieved chunk counts as
relevant if it comes from a labelled page of a labelled source. Pages are what a
citation points to, and they are stable when chunk sizes change between experiments.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean

Unit = tuple[str, int]  # (source title, page number)


@dataclass(frozen=True)
class Retrieved:
    source: str
    page: int | None


def relevant_units(labels: Sequence[dict]) -> set[Unit]:
    """Expand [{"source": s, "pages": [1, 2]}] into {(s, 1), (s, 2)}."""
    return {(label["source"], page) for label in labels for page in label["pages"]}


def _is_relevant(item: Retrieved, units: set[Unit]) -> bool:
    return item.page is not None and (item.source, item.page) in units


def hit_at_k(ranked: Sequence[Retrieved], units: set[Unit], k: int) -> float:
    """1 if any of the top k results is relevant, else 0."""
    return float(any(_is_relevant(r, units) for r in ranked[:k]))


def reciprocal_rank(ranked: Sequence[Retrieved], units: set[Unit], k: int = 10) -> float:
    """1 / rank of the first relevant result within the top k (0 if none)."""
    for rank, item in enumerate(ranked[:k], start=1):
        if _is_relevant(item, units):
            return 1.0 / rank
    return 0.0


def precision_at_k(ranked: Sequence[Retrieved], units: set[Unit], k: int) -> float:
    """Share of the top k results that are relevant."""
    return sum(_is_relevant(r, units) for r in ranked[:k]) / k


def page_recall_at_k(ranked: Sequence[Retrieved], units: set[Unit], k: int) -> float:
    """Share of the labelled (source, page) units that appear in the top k."""
    found = {(r.source, r.page) for r in ranked[:k] if _is_relevant(r, units)}
    return len(found) / len(units)


def source_recall_at_k(ranked: Sequence[Retrieved], units: set[Unit], k: int) -> float:
    """Share of the labelled sources with at least one relevant result in the top k.
    The key measure for multi-source and conflicting-evidence questions."""
    sources = {source for source, _ in units}
    found = {r.source for r in ranked[:k] if _is_relevant(r, units)}
    return len(found) / len(sources)


def score_question(ranked: Sequence[Retrieved], labels: Sequence[dict], ks: Sequence[int]) -> dict:
    units = relevant_units(labels)
    scores: dict[str, float] = {"mrr@10": reciprocal_rank(ranked, units, 10)}
    for k in ks:
        scores[f"hit@{k}"] = hit_at_k(ranked, units, k)
        scores[f"precision@{k}"] = precision_at_k(ranked, units, k)
        scores[f"page_recall@{k}"] = page_recall_at_k(ranked, units, k)
        scores[f"source_recall@{k}"] = source_recall_at_k(ranked, units, k)
    return scores


def average(per_question: Sequence[dict]) -> dict[str, float]:
    """Mean of each metric across questions."""
    if not per_question:
        return {}
    return {key: round(mean(q[key] for q in per_question), 3) for key in per_question[0]}


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile (pct in 0-100)."""
    ordered = sorted(values)
    rank = math.ceil(pct / 100 * len(ordered))  # 1-based
    return ordered[max(rank, 1) - 1]
