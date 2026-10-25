"""Turn extracted PDF page text into retrieval-sized chunks.

Design rules:
- A chunk never spans two pages, so every citation points to exactly one page.
- Chunks are built from whole sentences, preferring to end at paragraph breaks.
- Consecutive chunks on a page overlap by a few sentences, so a fact that straddles a
  boundary still appears whole in at least one chunk.
- A tiny leftover at the end of a page is merged into the previous chunk instead of
  becoming a near-empty chunk that would match searches by accident.
- Page furniture (running headers, footers, page numbers) is removed, and chunks that
  are almost all numbers (flattened tables and chart axes) are dropped: they match
  keyword searches on repeated labels but can't support a readable citation.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-based, as printed in a PDF viewer
    text: str


@dataclass(frozen=True)
class Chunk:
    index: int  # position within the whole document
    page_number: int
    text: str


# "retriev-\nal" -> "retrieval". Only when a lowercase letter continues the word, which
# is how line-break hyphenation looks. Rare compounds split exactly at a line end
# ("long-\ncontext") lose their hyphen; an acceptable trade for clean text.
_LINE_BREAK_HYPHEN = re.compile(r"(\w)-\n([a-z])")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# Split after . ! ? when the next sentence starts with a capital, digit, or bracket.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")


# A line that is only a page number: "12", "Page 12", "12 of 30", "- 12 -".
_PAGE_NUMBER_LINE = re.compile(r"[-–\s]*(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?[-–\s]*", re.I)
# A real word: a letter followed by at least two lowercase letters, maybe with punctuation.
_PROSE_WORD = re.compile(r"[A-Za-z][a-z]{2,}[.,;:)]?")


def remove_repeated_lines(
    pages: list[str], min_share: float = 0.5, max_len: int = 120
) -> list[str]:
    """Drop running headers, footers and page numbers from raw page texts.

    A short line that appears, word for word, on at least `min_share` of the pages (and
    at least 3) is page furniture, e.g. "Published as a conference paper at ICLR 2024".
    Lines that are only a page number all count as the same line, since the number
    changes on every page. Other digits are compared exactly, so "Table 3 shows..." on
    a few pages is never mistaken for a header.
    """
    if len(pages) < 3:
        return pages

    def key(line: str) -> str:
        line = " ".join(line.split())
        return "<page-number>" if _PAGE_NUMBER_LINE.fullmatch(line) else line.lower()

    page_counts = Counter(
        k for page in pages for k in {key(line) for line in page.splitlines() if line.strip()}
    )
    threshold = max(3, min_share * len(pages))
    repeated = {k for k, n in page_counts.items() if n >= threshold and len(k) <= max_len}
    return [
        "\n".join(line for line in page.splitlines() if key(line) not in repeated) for page in pages
    ]


def prose_ratio(text: str) -> float:
    """Share of tokens that are ordinary words. Body text is usually 0.5-0.8; a
    flattened results table ("23.5 14.0 5.8 46.1 ...") is close to 0."""
    tokens = text.split()
    return sum(bool(_PROSE_WORD.fullmatch(t)) for t in tokens) / max(len(tokens), 1)


def clean_page_text(raw: str) -> str:
    """Fix PDF extraction artifacts; keep paragraph breaks as blank lines."""
    # NFKC turns typographic ligatures into plain letters ("ﬁne-tuning" -> "fine-tuning"),
    # so keyword search finds them. Papers use ligatures heavily.
    text = unicodedata.normalize("NFKC", raw).replace("\x00", "")
    text = _LINE_BREAK_HYPHEN.sub(r"\1\2", text)
    paragraphs = (" ".join(p.split()) for p in _PARAGRAPH_BREAK.split(text))
    return "\n\n".join(p for p in paragraphs if p)


def _split_long(text: str, max_len: int) -> list[str]:
    """Break text with no usable sentence ends (tables, reference lists) at word boundaries."""
    pieces, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > max_len:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        pieces.append(current)
    return pieces


def _sentences(paragraph: str, max_len: int) -> list[str]:
    units = []
    for sentence in _SENTENCE_END.split(paragraph):
        units.extend(_split_long(sentence, max_len) if len(sentence) > max_len else [sentence])
    return units


def _joined_len(units: list[str]) -> int:
    return sum(len(u) for u in units) + max(len(units) - 1, 0)


def _chunk_page(text: str, size: int, overlap: int, min_size: int) -> list[str]:
    # Each chunk is a list of sentences; `carried` counts how many leading sentences
    # were copied from the previous chunk as overlap.
    chunks: list[tuple[list[str], int]] = []
    current: list[str] = []
    carried = 0

    def flush() -> None:
        nonlocal current, carried
        if len(current) == carried:  # nothing new beyond the overlap
            return
        chunks.append((current, carried))
        tail: list[str] = []
        for sentence in reversed(current):
            if _joined_len([sentence, *tail]) > overlap:
                break
            tail.insert(0, sentence)
        current, carried = list(tail), len(tail)

    for paragraph in text.split("\n\n"):
        # Prefer to end a chunk at a paragraph break once it's reasonably full.
        if _joined_len(current) >= size // 2:
            flush()
        for sentence in _sentences(paragraph, size):
            # Close the chunk when the next sentence won't fit, unless that would leave a
            # tiny chunk (e.g. a table header like "Model av." before a long table row);
            # then let it run over size instead.
            too_big = _joined_len([*current, sentence]) > size
            if current and too_big and _joined_len(current[carried:]) >= min_size:
                flush()
            current.append(sentence)
    flush()

    # Merge a tiny final chunk into the previous one, skipping the duplicated overlap.
    if len(chunks) > 1 and _joined_len(chunks[-1][0][chunks[-1][1] :]) < min_size:
        last, last_carried = chunks.pop()
        prev, prev_carried = chunks.pop()
        chunks.append((prev + last[last_carried:], prev_carried))

    return [" ".join(sentences) for sentences, _ in chunks]


def chunk_pages(
    pages: list[PageText],
    size: int = 1200,
    overlap: int = 200,
    min_size: int = 200,
    min_prose_ratio: float = 0.0,
) -> list[Chunk]:
    """Chunk every page. Chunks whose prose_ratio is below `min_prose_ratio` are left
    out (0 keeps everything)."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    chunks: list[Chunk] = []
    for page in pages:
        if not page.text.strip():
            continue
        for text in _chunk_page(page.text, size, overlap, min_size):
            if prose_ratio(text) < min_prose_ratio:
                continue
            chunks.append(Chunk(index=len(chunks), page_number=page.page_number, text=text))
    return chunks
