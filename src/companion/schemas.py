"""
Frozen data contracts shared across all pipeline stages.
DO NOT change field names without updating the UI, eval harness, and any callers.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Ingestion layer
# ---------------------------------------------------------------------------

class Document(BaseModel):
    """Raw document as loaded from the corpus."""
    doc_id: str = Field(default_factory=_uuid)
    text: str
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """A contiguous slice of a Document produced by a Chunker."""
    chunk_id: str = Field(default_factory=_uuid)
    doc_id: str
    text: str
    chunk_index: int
    char_start: int = Field(0)   # offset absoluto en el texto canónico
    char_end:   int = Field(0)   # offset absoluto en el texto canónico
    metadata: dict[str, Any] = Field(default_factory=dict)
    

class EnrichedChunk(BaseModel):
    """
    Output of an Enricher.

    The Enricher decides which content goes into `embedded_text` (what the
    Embedder sees) and what goes into `metadata` (stored as filterable fields
    in the vector store).  `original_text` is always preserved.
    """
    chunk_id: str
    doc_id: str
    original_text: str
    embedded_text: str   # fed to the Embedder
    metadata: dict[str, Any] = Field(default_factory=dict)
    enricher_name: str


# ---------------------------------------------------------------------------
# Query-time contract  — frozen; UI and eval harness both depend on this shape
# ---------------------------------------------------------------------------

class RetrievedDoc(BaseModel):
    chunk_id: str
    text: str
    score: float
    char_start: int = Field(0)
    char_end:   int = Field(0)
    metadata: dict[str, Any] = Field(default_factory=dict)


# class QueryResult(BaseModel):
#     """
#     Return value of answer().  Emit everything any plausible metric needs.
#     Do not remove or rename fields without coordinating with UI + eval owners.
#     """
#     query: str
#     answer: str
#     retrieved_docs: list[RetrievedDoc]
#     context_used: str   # the assembled context string passed to the generator
#     variant: str
