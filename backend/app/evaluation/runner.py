"""Run a benchmark question set against each retrieval mode and report metrics.

Usage (inside the api container, or via `make eval`):
    python -m app.evaluation.runner --benchmark /eval/benchmark_v1.json

Writes a JSON file with every question's results and a Markdown summary to
/eval/results/, and prints the comparison table.
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import DocumentChunk, ResearchProject, SourceDocument
from app.db.session import SessionLocal, engine
from app.embeddings import get_embedder
from app.evaluation.metrics import Retrieved, average, percentile, score_question
from app.retrieval.service import FUSION_CANDIDATES, RRF_K, SEARCH_FUNCTIONS

KS = (5, 10)
DEPTH = max(KS)  # how many results each question retrieves
DEFAULT_PROJECT = "RAG vs long-context LLMs"
TABLE_COLUMNS = [
    "hit@5",
    "hit@10",
    "mrr@10",
    "precision@5",
    "page_recall@10",
    "source_recall@10",
]


async def _find_project(session, title: str) -> ResearchProject:
    project = await session.scalar(
        select(ResearchProject)
        .where(ResearchProject.title == title)
        .order_by(ResearchProject.created_at.desc())
        .limit(1)
    )
    if project is None:
        raise SystemExit(f"No project titled {title!r}. Run `make ingest-corpus` first.")
    return project


async def _run_mode(session, project_id, mode: str, questions: list[dict]) -> dict:
    search = SEARCH_FUNCTIONS[mode]
    per_question = []
    for q in questions:
        started = time.perf_counter()
        ranked = await search(session, project_id, q["question"], DEPTH)
        latency_ms = (time.perf_counter() - started) * 1000
        await session.rollback()  # end the transaction so SET LOCAL settings don't leak

        record = {
            "id": q["id"],
            "type": q["type"],
            "latency_ms": round(latency_ms, 1),
            "top_score": ranked[0].score if ranked else None,
            "top5": [f"{r.source_title} p{r.page_number}" for r in ranked[:5]],
        }
        if q["relevant"]:
            items = [Retrieved(r.source_title, r.page_number) for r in ranked]
            record["scores"] = score_question(items, q["relevant"], KS)
        per_question.append(record)

    answerable = [r for r in per_question if "scores" in r]
    types = sorted({r["type"] for r in answerable})
    latencies = [r["latency_ms"] for r in per_question]
    unanswerable_scores = [
        r["top_score"] for r in per_question if "scores" not in r and r["top_score"] is not None
    ]
    return {
        "summary": {
            "overall": average([r["scores"] for r in answerable]),
            "by_type": {
                t: average([r["scores"] for r in answerable if r["type"] == t]) for t in types
            },
            "latency_ms": {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95)},
            "mean_top_score": {
                "answerable": round(mean(r["top_score"] for r in answerable if r["top_score"]), 4),
                "unanswerable": round(mean(unanswerable_scores), 4)
                if unanswerable_scores
                else None,
            },
        },
        "questions": per_question,
    }


def _markdown(report: dict) -> str:
    meta, results = report["meta"], report["results"]
    lines = [
        f"# Retrieval evaluation: {meta['benchmark']}",
        "",
        f"- **Run:** {meta['run_at']}",
        f"- **Labels:** {meta['review_status']}"
        + (
            " (numbers are provisional until reviewed)"
            if meta["review_status"] != "reviewed"
            else ""
        ),
        f"- **Questions:** {meta['question_counts']}",
        f"- **Corpus:** {meta['corpus']['sources']} sources, {meta['corpus']['chunks']} chunks",
        f"- **Embedding model:** {meta['embedding_model']}",
        f"- **Chunking:** {meta['chunking']}",
        f"- **Hybrid:** RRF k={meta['rrf_k']}, {meta['fusion_candidates']} candidates per method",
        "",
        "## Overall (answerable questions)",
        "",
        "| Mode | " + " | ".join(TABLE_COLUMNS) + " | p50 ms | p95 ms |",
        "|---|" + "---|" * (len(TABLE_COLUMNS) + 2),
    ]
    for mode, data in results.items():
        s = data["summary"]
        cells = [f"{s['overall'].get(c, 0):.3f}" for c in TABLE_COLUMNS]
        lines.append(
            f"| {mode} | "
            + " | ".join(cells)
            + f" | {s['latency_ms']['p50']:.0f} | {s['latency_ms']['p95']:.0f} |"
        )

    types = sorted({t for d in results.values() for t in d["summary"]["by_type"]})
    lines += [
        "",
        "## By question type (hit@5 / source_recall@10)",
        "",
        "| Mode | " + " | ".join(types) + " |",
        "|---|" + "---|" * len(types),
    ]
    for mode, data in results.items():
        by_type = data["summary"]["by_type"]
        cells = [
            f"{by_type[t]['hit@5']:.2f} / {by_type[t]['source_recall@10']:.2f}"
            if t in by_type
            else "-"
            for t in types
        ]
        lines.append(f"| {mode} | " + " | ".join(cells) + " |")

    lines += ["", "## Misses at 5 (no relevant result in the top 5)", ""]
    for mode, data in results.items():
        misses = [q["id"] for q in data["questions"] if q.get("scores", {}).get("hit@5") == 0.0]
        lines.append(f"- **{mode}:** {', '.join(misses) or 'none'}")
    return "\n".join(lines) + "\n"


async def run(spec: dict, modes: list[str], project_title: str) -> dict:
    """Score every question in `spec` with each mode. Database work only; file I/O lives
    in main() so this coroutine never blocks the event loop."""
    questions = spec["questions"]
    settings = get_settings()

    async with SessionLocal() as session:
        project = await _find_project(session, project_title)
        # Copy the plain value now: the rollback after each question expires ORM objects,
        # and reading project.id later would trigger a lazy (sync) reload -> MissingGreenlet.
        project_id = project.id
        sources = await session.scalar(
            select(func.count())
            .select_from(SourceDocument)
            .where(SourceDocument.project_id == project_id)
        )
        chunks = await session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .join(SourceDocument)
            .where(SourceDocument.project_id == project_id)
        )
        # Load the model before timing anything, so latency excludes the one-off load.
        await asyncio.to_thread(get_embedder().embed_query, "warm up")
        results = {mode: await _run_mode(session, project_id, mode, questions) for mode in modes}
    await engine.dispose()

    counts: dict[str, int] = {}
    for q in questions:
        counts[q["type"]] = counts.get(q["type"], 0) + 1
    report = {
        "meta": {
            "benchmark": spec["version"],
            "review_status": spec.get("review_status", "draft"),
            "run_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            "question_counts": counts,
            "corpus": {"project": project_title, "sources": sources, "chunks": chunks},
            "embedding_model": settings.embedding_model,
            "chunking": {
                "size": settings.chunk_size,
                "overlap": settings.chunk_overlap,
                "min_size": settings.chunk_min_size,
                "min_prose_ratio": settings.chunk_min_prose_ratio,
            },
            "rrf_k": RRF_K,
            "fusion_candidates": FUSION_CANDIDATES,
            "depth": DEPTH,
        },
        "results": results,
    }

    return report


def write_report(report: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    stem = f"{report['meta']['benchmark']}__{stamp}"
    markdown = _markdown(report)
    (out_dir / f"{stem}.json").write_text(json.dumps(report, indent=1))
    (out_dir / f"{stem}.md").write_text(markdown)
    (out_dir / "latest.md").write_text(markdown)
    print(markdown)
    print(f"Saved {out_dir / stem}.json and .md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--benchmark", type=Path, default=Path("/eval/benchmark_v1.json"))
    parser.add_argument("--modes", default="semantic,keyword,hybrid")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="project title")
    parser.add_argument("--out", type=Path, default=Path("/eval/results"))
    args = parser.parse_args()
    spec = json.loads(args.benchmark.read_text())
    report = asyncio.run(run(spec, args.modes.split(","), args.project))
    write_report(report, args.out)


if __name__ == "__main__":
    main()
