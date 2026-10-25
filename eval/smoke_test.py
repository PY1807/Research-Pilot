"""Run the M2 smoke questions against the live search API and report hits.

Usage: python3 eval/smoke_test.py [--k 5] [--mode hybrid|semantic|keyword] [--project <id>]
Uses only the standard library, so it runs from the host without the backend venv.
"""

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

API = "http://localhost:8000/api"


def get(path: str):
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "semantic", "keyword"])
    parser.add_argument("--project", help="project id (default: the most recent project)")
    args = parser.parse_args()

    spec = json.loads((Path(__file__).parent / "smoke_questions.json").read_text())
    project_id = args.project or get("/projects/")[0]["id"]

    hits = 0
    for q in spec["questions"]:
        params = urllib.parse.urlencode({"q": q["question"], "k": args.k, "mode": args.mode})
        results = get(f"/projects/{project_id}/search/?{params}")
        rank = next(
            (
                i
                for i, r in enumerate(results, start=1)
                if r["source_title"] == q["source"] and r["page_number"] in q["pages"]
            ),
            None,
        )
        hits += rank is not None
        top = results[0] if results else None
        mark = f"HIT @{rank}" if rank else "MISS  "
        top_desc = f"{top['source_title'][:34]} p{top['page_number']}" if top else "-"
        print(f"{mark:7} {q['id']}  expected {q['source'][:34]:34}  top: {top_desc}")

    total = len(spec["questions"])
    print(f"\nHit rate @{args.k} ({args.mode}): {hits}/{total} ({hits / total:.0%})")


if __name__ == "__main__":
    main()
