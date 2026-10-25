"""Write the ticks from a reviewed sheet back into the benchmark's labels.

Usage: python -m app.evaluation.apply_review --benchmark /eval/benchmark_v1.json
Reads /eval/review/<benchmark>_review.md, replaces each question's `relevant` labels with
the ticked pages, and marks the benchmark as reviewed.
"""

import argparse
import json
import re
from pathlib import Path

QUESTION = re.compile(r"^## (\w+) \(")
TICKED = re.compile(r"^- \[[xX]\] (\S+) p(\d+)")


def parse_sheet(text: str) -> dict[str, dict[str, set[int]]]:
    """{question id: {source: {pages}}} for every ticked line."""
    ticks: dict[str, dict[str, set[int]]] = {}
    current = None
    for line in text.splitlines():
        if m := QUESTION.match(line):
            current = m.group(1)
            ticks[current] = {}
        elif current and (m := TICKED.match(line)):
            ticks[current].setdefault(m.group(1), set()).add(int(m.group(2)))
    return ticks


def apply(spec: dict, ticks: dict[str, dict[str, set[int]]]) -> list[str]:
    changes = []
    for q in spec["questions"]:
        if q["id"] not in ticks:
            continue
        new = [{"source": s, "pages": sorted(p)} for s, p in sorted(ticks[q["id"]].items())]
        if new != sorted(q["relevant"], key=lambda r: r["source"]):
            changes.append(q["id"])
        q["relevant"] = new
        if not new and q["type"] != "unanswerable":
            q["type"] = "unanswerable"
        elif new and q["type"] == "unanswerable":
            q["type"] = "fact" if len(new) == 1 else "multi"
    spec["review_status"] = "reviewed"
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--benchmark", type=Path, default=Path("/eval/benchmark_v1.json"))
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    review = args.review or Path("/eval/review") / f"{args.benchmark.stem}_review.md"
    spec = json.loads(args.benchmark.read_text())
    changes = apply(spec, parse_sheet(review.read_text()))
    args.benchmark.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Updated {len(changes)} questions: {', '.join(changes) or 'none'}")


if __name__ == "__main__":
    main()
