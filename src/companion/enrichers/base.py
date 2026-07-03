from __future__ import annotations
from abc import ABC, abstractmethod
from companion.schemas import Chunk, EnrichedChunk


class Enricher(ABC):
    """
    THE EXPERIMENTAL VARIABLE.

    Transforms a Chunk into an EnrichedChunk by deciding:
      - embedded_text  : the text the Embedder will encode (may include synthetic context)
      - metadata       : filterable fields stored alongside the vector but NOT embedded

    `doc_text` is the full parent-document text, passed so enrichers that need
    document-level context (SummaryEnricher) can use it.  Pass "" if unavailable.

    Downstream (Embedder, VectorStore, Retriever, Generator) is identical across
    all Enricher implementations — only this class changes between variants.
    """

    name: str  # declared by each subclass

    @abstractmethod
    def enrich(self, chunk: Chunk, doc_text: str = "") -> EnrichedChunk:
        """Return an EnrichedChunk derived from chunk."""
