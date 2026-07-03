from __future__ import annotations
from abc import ABC, abstractmethod
from companion.schemas import Chunk, Document


class Chunker(ABC):
    @abstractmethod
    def chunk(self, document: Document) -> list[Chunk]:
        """Split a Document into a list of Chunks."""
