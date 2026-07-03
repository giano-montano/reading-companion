from __future__ import annotations
from abc import ABC, abstractmethod
from companion.schemas import EnrichedChunk, RetrievedDoc


class VectorStore(ABC):
    @abstractmethod
    def add(
        self,
        chunks: list[EnrichedChunk],
        embeddings: list[list[float]],
        variant: str,
    ) -> None:
        """Persist chunks and their embeddings under the given variant collection."""

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        variant: str,
        top_k: int,
    ) -> list[RetrievedDoc]:
        """Return top_k results from the variant collection."""

    @abstractmethod
    def clear(self, variant: str) -> None:
        """Delete and recreate the variant collection."""

    @abstractmethod
    def collection_exists(self, variant: str) -> bool:
        """Return True if the variant collection exists and is non-empty."""
