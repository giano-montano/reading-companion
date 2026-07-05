"""
ScopeResolver — deterministic, offset-based selection of chunks.

Scoping is NOT retrieval: no embedding, no vector search, no LLM.  It is a pure
metadata filter over a catalog of chunk descriptors (`ChunkRef`) whose offsets
are absolute over the canonical text.  The resolver NEVER computes the viewport
range or the section — the frontend sends those; the resolver only filters.

Text hydration is done by slicing the canonical string:
`ScopeChunk.text == canonical_text[char_start:char_end]`.  This is the ONLY
place text is produced, so there can never be a second normalization that
desyncs the offsets (contracts #1 and #2).

Four modes:
  * 'lo_que_veo'  — chunks intersecting a [range_start, range_end] viewport.
  * 'seccion'     — chunks belonging to one section_id.
  * 'hasta_aqui'  — chunks up to and including max_progress_section (anti-spoiler).
  * 'obra'        — every chunk in the work.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from companion.agent.tools.contracts import ScopeChunk


class ChunkRef(BaseModel):
    """
    Catalog entry: the minimum needed to place a chunk without loading its text.
    Produced by the indexing job (from Chunk metadata) and fed to the resolver.
    """
    chunk_id: str
    section: int                 # ordered section index; comparable to progress
    char_start: int = Field(0)   # absolute offset in the canonical text
    char_end: int = Field(0)     # absolute offset in the canonical text
    chunk_index: int = Field(0)  # position in reading order


class ScopeMode(str, Enum):
    VISIBLE = "lo_que_veo"
    SECTION = "seccion"
    UP_TO_HERE = "hasta_aqui"
    WORK = "obra"


class ScopeRequest(BaseModel):
    """
    Frontend-supplied scope request.  Only the fields relevant to `mode` are
    used; the resolver validates that they are present.
    """
    mode: ScopeMode
    range_start: int | None = None          # 'lo_que_veo'
    range_end: int | None = None            # 'lo_que_veo'
    section_id: int | None = None           # 'seccion'
    max_progress_section: int | None = None  # 'hasta_aqui'

    @model_validator(mode="after")
    def _check_required(self) -> "ScopeRequest":
        if self.mode is ScopeMode.VISIBLE:
            if self.range_start is None or self.range_end is None:
                raise ValueError("mode 'lo_que_veo' requires range_start and range_end")
            if self.range_end < self.range_start:
                raise ValueError("range_end must be >= range_start")
        elif self.mode is ScopeMode.SECTION:
            if self.section_id is None:
                raise ValueError("mode 'seccion' requires section_id")
        elif self.mode is ScopeMode.UP_TO_HERE:
            if self.max_progress_section is None:
                raise ValueError("mode 'hasta_aqui' requires max_progress_section")
        return self


class ScopeResolver:
    """
    Resolves a `ScopeRequest` to an ordered `list[ScopeChunk]`.

    Args:
        catalog: chunk descriptors for the whole work.
        canonical_text: the exact string produced by TextLoader.load(); the same
            string the frontend renders.  Used to slice chunk text by offset.
    """

    def __init__(self, catalog: list[ChunkRef], canonical_text: str) -> None:
        # Reading order is the ground truth for every mode's output ordering.
        self._catalog = sorted(catalog, key=lambda c: (c.char_start, c.chunk_index))
        self._canonical = canonical_text

    # -- public API ---------------------------------------------------------

    def resolve(self, request: ScopeRequest) -> list[ScopeChunk]:
        if request.mode is ScopeMode.VISIBLE:
            return self.visible(request.range_start, request.range_end)
        if request.mode is ScopeMode.SECTION:
            return self.section(request.section_id)
        if request.mode is ScopeMode.UP_TO_HERE:
            return self.up_to(request.max_progress_section)
        return self.work()

    def visible(self, range_start: int, range_end: int) -> list[ScopeChunk]:
        """Chunks intersecting the half-open viewport [range_start, range_end).

        A chunk (with half-open [char_start, char_end)) intersects when it
        starts before the range ends and ends after the range starts.
        """
        return self._collect(
            c for c in self._catalog
            if c.char_start < range_end and c.char_end > range_start
        )

    def section(self, section_id: int) -> list[ScopeChunk]:
        return self._collect(c for c in self._catalog if c.section == section_id)

    def up_to(self, max_progress_section: int) -> list[ScopeChunk]:
        """Anti-spoiler window: everything up to and including max progress (C)."""
        return self._collect(
            c for c in self._catalog if c.section <= max_progress_section
        )

    def work(self) -> list[ScopeChunk]:
        return self._collect(iter(self._catalog))

    # -- internals ----------------------------------------------------------

    def _collect(self, refs) -> list[ScopeChunk]:
        return [
            ScopeChunk(
                chunk_id=ref.chunk_id,
                char_start=ref.char_start,
                char_end=ref.char_end,
                text=self._canonical[ref.char_start:ref.char_end],
                score=None,
            )
            for ref in refs
        ]
