"""Build a Markdown review sheet for labelling a benchmark.

For each question, pool the top results from every search mode (the standard way IR
benchmarks are labelled), group them by (source, page), and show each passage with a
checkbox. Pages already labelled relevant are pre-ticked. A reviewer reads each
passage, fixes the ticks, then `apply_review` writes the ticks back to the benchmark.

Usage: python -m app.evaluation.review_sheet --benchmark /eval/benchmark_v1.json
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.db.session import SessionLocal, engine
from app.evaluation.runner import DEFAULT_PROJECT, _find_project
from app.retrieval.service import SEARCH_FUNCTIONS

POOL_DEPTH = 5
SNIPPET_CHARS = 420

INSTRUCTIONS = """\
# Labelling review: {version}

**How to review (about 3-5 minutes per question):**
1. Read the question, then each passage below it.
2. Tick `[x]` if that page **directly answers** the question (or, for conflict questions,
   states one side of the disagreement). Untick `[ ]` if it doesn't.
3. Missing a page you know answers it? Add a line: `- [x] <source title> p<page>`.
4. Unanswerable questions should end with no ticks. If a passage does answer one,
   tick it; the question then becomes answerable.
5. Save the file and tell Claude; `apply_review` writes your ticks into the benchmark.

`found by` shows which search methods returned the passage in their top {depth}.
"""


async def build(spec: dict, project_title: str) -> str:
    lines = [INSTRUCTIONS.format(version=spec["version"], depth=POOL_DEPTH)]
    async with SessionLocal() as session:
        project_id = (await _find_project(session, project_title)).id
        for q in spec["questions"]:
            labelled = {(r["source"], p) for r in q["relevant"] for p in r["pages"]}
            pooled: dict[tuple[str, int], dict] = {}
            for mode, search in SEARCH_FUNCTIONS.items():
                for result in await search(session, project_id, q["question"], POOL_DEPTH):
                    key = (result.source_title, result.page_number)
                    entry = pooled.setdefault(key, {"modes": [], "text": result.text})
                    if mode not in entry["modes"]:  # two chunks from one page: list once
                        entry["modes"].append(mode)
                await session.rollback()

            lines += [
                "---",
                "",
                f"## {q['id']} ({q['type']}): {q['question']}",
                "",
            ]
            for (source, page), entry in sorted(pooled.items()):
                tick = "x" if (source, page) in labelled else " "
                snippet = " ".join(entry["text"].split())[:SNIPPET_CHARS]
                lines += [
                    f"- [{tick}] {source} p{page}  · found by: {', '.join(entry['modes'])}",
                    f"  > {snippet}…",
                ]
            missing = sorted(labelled - set(pooled))
            for source, page in missing:
                lines.append(f"- [x] {source} p{page}  · labelled, but no method found it")
            lines.append("")
    await engine.dispose()
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--benchmark", type=Path, default=Path("/eval/benchmark_v1.json"))
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--out", type=Path, default=Path("/eval/review"))
    args = parser.parse_args()
    spec = json.loads(args.benchmark.read_text())
    sheet = asyncio.run(build(spec, args.project))
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.benchmark.stem}_review.md"
    path.write_text(sheet)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
