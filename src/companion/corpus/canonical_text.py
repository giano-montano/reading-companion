"""
Canonical-text builder.

The single source of truth for what "canonical text" means.  If this changes,
all char_start/char_end offsets persisted in Chroma become invalid (contract #1).

Canonical text = chunks' `text` joined by "\\n\\n" in reading order.
"""
from __future__ import annotations

from companion.corpus.book_master import BookChunk, BookMaster


def build_canonical_text(chunks: list[BookChunk]) -> str:
    return "\n\n".join(c.text for c in chunks)


def recompute_offsets(master: BookMaster) -> BookMaster:
    """
    Recompute `char_start` / `char_end` / `token_count` on every chunk from
    the canonical text.  Returns the same master (mutated) for convenience.
    """
    cursor = 0
    for i, chunk in enumerate(master.chunks):
        chunk.text = canonical_slice_for_chunk(master.chunks, i)
        chunk.char_start = cursor
        chunk.char_end = cursor + len(chunk.text)
        chunk.token_count = _token_count(chunk.text)
        cursor = chunk.char_end + 2  # for the "\n\n" separator
    for chunk in master.chunks:
        for block in master.blocks:
            if block.chunk_id == chunk.id and block.is_narrative:
                block.token_count = chunk.token_count  # informational only
    return master


def canonical_slice_for_chunk(chunks: list[BookChunk], idx: int) -> str:
    """
    Return the canonical slice for chunks[idx].  This is a pure function over
    the chunks' `text` field; it does NOT recompute the text itself.

    Use this when validating that a stored offset still matches the current
    chunk text.
    """
    return chunks[idx].text


def _token_count(text: str) -> int:
    # proxy: words × 1.3 — good enough for Spanish at MVP scale
    return int(round(len(text.split()) * 1.3))


def validate_offsets(master: BookMaster) -> None:
    """
    Assert that canonical[chunk.char_start:chunk.char_end] == chunk.text
    for every chunk.  Raises AssertionError with the first mismatch.
    """
    canonical = build_canonical_text(master.chunks)
    for c in master.chunks:
        slice_ = canonical[c.char_start : c.char_end]
        if slice_ != c.text:
            raise AssertionError(
                f"Chunk {c.id} offset mismatch: "
                f"canonical[{c.char_start}:{c.char_end}] != chunk.text. "
                f"Got {slice_[:80]!r}... expected {c.text[:80]!r}..."
            )
