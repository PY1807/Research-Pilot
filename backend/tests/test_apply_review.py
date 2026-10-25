from app.evaluation.apply_review import apply, parse_sheet

SHEET = """\
# Labelling review

## f01 (fact): What two kinds of memory?

- [x] paperA p1  · found by: semantic
  > passage text…
- [ ] paperA p9  · found by: keyword
- [X] paperB p3  · found by: hybrid

## u01 (unanswerable): Something not covered?

- [ ] paperC p2  · found by: semantic

## u02 (unanswerable): Actually covered?

- [x] paperD p4  · found by: keyword
"""


def test_parse_sheet_reads_only_ticked_lines():
    ticks = parse_sheet(SHEET)

    assert ticks == {"f01": {"paperA": {1}, "paperB": {3}}, "u01": {}, "u02": {"paperD": {4}}}


def test_apply_replaces_labels_and_fixes_types():
    spec = {
        "review_status": "draft",
        "questions": [
            {"id": "f01", "type": "fact", "relevant": [{"source": "paperA", "pages": [1, 2]}]},
            {"id": "u01", "type": "unanswerable", "relevant": []},
            {"id": "u02", "type": "unanswerable", "relevant": []},
            {"id": "f99", "type": "fact", "relevant": [{"source": "paperZ", "pages": [5]}]},
        ],
    }

    changes = apply(spec, parse_sheet(SHEET))

    by_id = {q["id"]: q for q in spec["questions"]}
    assert by_id["f01"]["relevant"] == [
        {"source": "paperA", "pages": [1]},
        {"source": "paperB", "pages": [3]},
    ]
    assert by_id["u02"]["type"] == "fact"  # a ticked page makes it answerable
    assert by_id["f99"]["relevant"] == [{"source": "paperZ", "pages": [5]}]  # not in sheet
    assert spec["review_status"] == "reviewed"
    assert set(changes) == {"f01", "u02"}
