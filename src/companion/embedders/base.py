from __future__ import annotations
from abc import ABC, abstractmethod


class Embedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single text."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Output vector dimension."""
