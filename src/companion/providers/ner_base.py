from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TypedDict


class Entity(TypedDict):
    text: str
    label: str
    start: int
    end: int


class NERProvider(ABC):
    @abstractmethod
    def extract_entities(self, text: str) -> list[Entity]:
        """Return named entities with span offsets."""
