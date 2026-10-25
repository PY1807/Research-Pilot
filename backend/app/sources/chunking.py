"""Turn extracted PDF page text into retrieval-sized chunks.

Design rules:
- A chunk never spans two pages, so every citation points to exactly one page.
- Chunks are built from whole sentences, preferring to end at paragraph breaks.
- Consecutive chunks on a page overlap by a few sentences, so a fact that straddles a
  boundary still appears whole in at least one chunk.
- A tiny leftover at the end of a page is merged into the previous chunk instead of
  becoming a near-empty chunk that would match searches by accident.
"""

import re
import unicodedata
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
    pages: list[PageText], size: int = 1200, overlap: int = 200, min_size: int = 200
) -> list[Chunk]:
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    chunks: list[Chunk] = []
    for page in pages:
        if not page.text.strip():
            continue
        for text in _chunk_page(page.text, size, overlap, min_size):
            chunks.append(Chunk(index=len(chunks), page_number=page.page_number, text=text))
    return chunks
