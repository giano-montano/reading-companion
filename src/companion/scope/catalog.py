"""
ChunkCatalog — deterministic chunk lookup for scope resolution (no embeddings).

Source of truth is the per-book `retrieval.jsonl` (already produced by the
preprocessing pipeline): every line carries `chunk_id`, `text`, and absolute
`char_start`/`char_end` in metadata.  The catalog translates any frontend
selector into an ordered list of chunks, so tools always receive chunks.

It is aligned to Chang's anti-spoiler axis: the chunk index is the integer
suffix of `book::chunk::N`, and `up_to_index` mirrors the QA-RAG gate.

Used by the image feature to turn "lo que veo / esta sección / hasta el máximo /
toda la obra" into the text that grounds the illustration.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

RETRIEVAL_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data" / "outputs" / "retrieval"
)


def _chunk_index(chunk_id: str) -> int:
    """Integer reading-order index from a 'book::chunk::N' id (0 if unparseable)."""
    try:
        return int(chunk_id.rsplit("::", 1)[-1])
    except (ValueError, IndexError):
        return 0


class CatalogChunk(BaseModel):
    chunk_id: str
    index: int
    char_start: int = Field(0)
    char_end: int = Field(0)
    text: str


class ChunkCatalog:
    """Ordered, in-memory index of one book's chunks."""

    def __init__(self, chunks: list[CatalogChunk]) -> None:
        self._chunks = sorted(chunks, key=lambda c: c.index)
        self._by_id = {c.chunk_id: c for c in self._chunks}

    # -- selectors ----------------------------------------------------------

    def by_ids(self, chunk_ids: list[str]) -> list[CatalogChunk]:
        """Chunks matching the given ids, returned in reading order.

        Unknown ids are silently skipped (the frontend may send stale ids)."""
        wanted = {cid for cid in chunk_ids}
        return [c for c in self._chunks if c.chunk_id in wanted]

    def up_to_index(self, max_index: int) -> list[CatalogChunk]:
        """Chunks with index <= max_index (the 'hasta el máximo' window)."""
        return [c for c in self._chunks if c.index <= max_index]

    def all(self) -> list[CatalogChunk]:
        return list(self._chunks)

    def __len__(self) -> int:
        return len(self._chunks)


def _load_catalog(book_id: str) -> ChunkCatalog:
    path = RETRIEVAL_DIR / f"{book_id}.retrieval.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No retrieval file for book '{book_id}': {path}")

    chunks: list[CatalogChunk] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            meta = row.get("metadata", {})
            chunk_id = row["chunk_id"]
            chunks.append(
                CatalogChunk(
                    chunk_id=chunk_id,
                    index=_chunk_index(chunk_id),
                    char_start=int(meta.get("char_start", 0)),
                    char_end=int(meta.get("char_end", 0)),
                    text=row.get("text", ""),
                )
            )
    return ChunkCatalog(chunks)


@lru_cache(maxsize=16)
def get_catalog(book_id: str) -> ChunkCatalog:
    """Cached per-book catalog (parsed once, reused across requests)."""
    return _load_catalog(book_id)


def build_scope_text(chunks: list[CatalogChunk], max_chars: int = 6000) -> str:
    """Concatenate chunk text for grounding an illustration, bounded to
    `max_chars`.

    A whole book is far too long (and expensive) to feed verbatim, and the image
    prompt only needs enough to depict a few scenes.  When the selection exceeds
    the budget, chunks are sampled EVENLY across reading order so the beginning,
    middle and end are all represented (matches the 'summarize begin/middle/end'
    instruction for wide scopes)."""
    if not chunks:
        return ""

    joined = "\n\n".join(c.text.strip() for c in chunks)
    if len(joined) <= max_chars:
        return joined

    # Evenly sample chunks across reading order, capping each piece so several
    # chunks fit, then hard-clamp the joined result to the char budget.
    per_chunk = max(1, max_chars // max(1, len(chunks)))
    step = max(1, len(chunks) // max(1, max_chars // per_chunk))

    parts = [c.text.strip()[:per_chunk] for c in chunks[::step]]
    return "\n\n".join(parts)[:max_chars]
