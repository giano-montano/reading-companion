from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import Iterator
from companion.schemas import Document


class CorpusLoader(ABC):
    @abstractmethod
    def load(self) -> Iterator[Document]:
        """Yield Document objects one at a time."""
