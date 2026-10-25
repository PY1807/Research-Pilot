import pytest

from app.sources.chunking import (
    PageText,
    chunk_pages,
    clean_page_text,
    prose_ratio,
    remove_repeated_lines,
)
from tests.pdfs import sentences


def test_clean_page_text_fixes_hyphenation_and_whitespace():
    raw = "Retriev-\nal augmented   generation\nworks well.\n\n  Second   paragraph.\x00"

    assert clean_page_text(raw) == "Retrieval augmented generation works well.\n\nSecond paragraph."


def test_clean_page_text_replaces_ligatures():
    assert clean_page_text("task-speciﬁc ﬁne-tuning") == "task-specific fine-tuning"


def test_chunks_never_cross_pages_and_are_numbered_in_order():
    pages = [
        PageText(1, sentences("First", 30)),
        PageText(2, sentences("Second", 30)),
        PageText(3, sentences("Third", 5)),
    ]

    chunks = chunk_pages(pages, size=600, overlap=100, min_size=100)

    assert [c.index for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        expected_prefix = {1: "First", 2: "Second", 3: "Third"}[chunk.page_number]
        assert chunk.text.startswith(expected_prefix)
        other_pages = {"First", "Second", "Third"} - {expected_prefix}
        assert all(word not in chunk.text for word in other_pages)
    assert {c.page_number for c in chunks} == {1, 2, 3}


def test_chunks_respect_size_and_overlap():
    page = PageText(1, sentences("Alpha", 40))

    chunks = chunk_pages([page], size=500, overlap=150, min_size=100)

    assert len(chunks) > 3
    longest_sentence = max(len(s) for s in page.text.split(". "))
    assert all(len(c.text) <= 500 + longest_sentence for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        # The next chunk starts by repeating the previous chunk's final sentence(s).
        last_sentence = prev.text.rsplit(". ", 1)[-1]
        first_sentence = nxt.text.split(". ", 1)[0] + "."
        assert last_sentence in nxt.text[: 150 + len(last_sentence)]
        assert prev.text.endswith(nxt.text[: nxt.text.index(last_sentence)] + last_sentence)
        assert first_sentence in prev.text


def test_text_without_sentence_breaks_is_split_at_word_boundaries():
    reference_list = " ".join(f"token{i}" for i in range(1000))

    chunks = chunk_pages([PageText(1, reference_list)], size=300, overlap=0, min_size=50)

    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)
    assert " ".join(c.text for c in chunks) == reference_list


def test_tiny_trailing_piece_is_merged_into_previous_chunk():
    text = sentences("Body", 9) + " Tail."

    chunks = chunk_pages([PageText(1, text)], size=300, overlap=0, min_size=100)

    assert chunks[-1].text.endswith("Tail.")
    assert all(len(c.text) >= 100 for c in chunks)


def test_short_fragment_before_long_run_is_not_left_alone():
    # A table header ending in a period, then a long run with no sentence breaks.
    table_row = " ".join(f"{i}.5" for i in range(200))
    text = f"Model av. {table_row}"

    chunks = chunk_pages([PageText(1, text)], size=300, overlap=0, min_size=100)

    assert chunks[0].text.startswith("Model av. 0.5")
    assert all(len(c.text) >= 100 for c in chunks)


def test_empty_pages_are_skipped():
    chunks = chunk_pages([PageText(1, ""), PageText(2, "Only page two has text.")])

    assert [c.page_number for c in chunks] == [2]


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_pages([PageText(1, "x")], size=100, overlap=100)


def test_repeated_headers_footers_and_page_numbers_are_removed():
    pages = [
        f"Published as a conference paper at ICLR 2024\nUnique content {i}.\n{i}"
        for i in range(1, 6)
    ]

    cleaned = remove_repeated_lines(pages)

    assert cleaned == [f"Unique content {i}." for i in range(1, 6)]


def test_lines_on_only_a_few_pages_are_kept():
    pages = ["Table 1: results\nA", "Table 1: results\nB", "C", "D", "E", "F"]

    assert remove_repeated_lines(pages) == pages


def test_short_documents_are_left_alone():
    assert remove_repeated_lines(["Header\nA", "Header\nB"]) == ["Header\nA", "Header\nB"]


def test_prose_ratio_separates_text_from_number_tables():
    assert prose_ratio("23.5 14.0 5.8 46.1 35.5 27.4 16.9 1.9") == 0.0
    assert prose_ratio("Long context models read whole books at once.") > 0.6


def test_number_only_chunks_can_be_dropped():
    pages = [PageText(1, "Real sentence about retrieval quality."), PageText(2, "1.0 2.0 3.0 4.0")]

    kept = chunk_pages(pages, min_prose_ratio=0.2)

    assert [c.page_number for c in kept] == [1]
    assert [c.index for c in kept] == [0]


def test_numbered_content_lines_are_not_mistaken_for_headers():
    pages = [f"Header\nTable {i} shows the results.\nPage {i} of 5" for i in range(1, 6)]

    assert remove_repeated_lines(pages) == [f"Table {i} shows the results." for i in range(1, 6)]
