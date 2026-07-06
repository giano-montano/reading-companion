"""
BookMaster — pydantic models that mirror `data/master/master.md` exactly.

This is the source of truth for the offline book-processing pipeline.  The
existing `companion.schemas.Chunk` / `EnrichedChunk` (F1) are NOT used here:
those describe the runtime RAG chunk, not the precomputed master.

Conventions (all frozen, see `data/master/master.md`):
  * book_id  : stable string id (snake_case of title in Spanish)
  * section_id, block_id, chunk_id : autoincrement ints within the book
  * chunk text is plain (no HTML); canonical_text = "\n\n".join(chunks)
  * char_start inclusive, char_end exclusive over the canonical text
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class BookMetadata(BaseModel):
    title: str
    author: str
    publication_year: int | None = None
    language: str | None = None


class BookSection(BaseModel):
    id: int


class BookBlock(BaseModel):
    """A visible unit in the rendered book.  `content` is small sanitized HTML."""
    id: int
    section_id: int | None = None
    content: str
    text: str = ""            # plain-text mirror of `content` (used by chunker)
    chunk_id: int | None = None
    is_narrative: bool = False
    token_count: int = 0


class BookChunk(BaseModel):
    """
    Retrieval unit.  May span multiple sections; `section_ids` lists them in
    reading order, without nulls.

    `start_block_id` / `end_block_id` are used internally by the chunker
    to build the block->chunk mapping; they are excluded from the published
    JSON (see master_writer.py).  Anti-spoiler is done by chunk_id.
    """
    id: int
    section_ids: list[int] = Field(default_factory=list)
    start_block_id: int = 0
    end_block_id: int = 0
    text: str
    char_start: int
    char_end: int
    token_count: int = 0

    @field_validator("section_ids")
    @classmethod
    def _no_nulls(cls, v: list[int]) -> list[int]:
        if any(s is None for s in v):  # type: ignore[comparison-overlap]
            raise ValueError("section_ids must not contain nulls")
        return v


class BookMaster(BaseModel):
    book_id: str
    metadata: BookMetadata
    sections: list[BookSection] = Field(default_factory=list)
    blocks: list[BookBlock] = Field(default_factory=list)
    chunks: list[BookChunk] = Field(default_factory=list)
