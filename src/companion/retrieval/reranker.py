from __future__ import annotations
from abc import ABC, abstractmethod
from companion.schemas import RetrievedDoc


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
        """Return docs re-sorted by relevance to query."""


class PassthroughReranker(Reranker):
    """No-op reranker.  Default: reranking is OFF."""

    def rerank(self, query: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
        return docs
