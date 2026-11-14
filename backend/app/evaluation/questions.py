"""Load a question set for evaluation. Benchmark files have {id, type, question,
relevant}; the M2 smoke file has {id, question, source, pages}. Both come back in the
benchmark shape, so every eval script accepts either file."""

import json
from pathlib import Path


def load_questions(path: Path) -> tuple[dict, list[dict]]:
    spec = json.loads(path.read_text())
    spec.setdefault("version", path.stem)
    questions = []
    for q in spec["questions"]:
        if "relevant" not in q:
            q = {**q, "type": "fact", "relevant": [{"source": q["source"], "pages": q["pages"]}]}
        questions.append(q)
    return spec, questions
