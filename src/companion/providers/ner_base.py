from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TypedDict


class Entity(TypedDict):
    text: str
    label: str
    start: int
    end: int
    # POS-cleaned surface: only the proper-noun tokens of the span, with a
    # leading honorific attached ("El señor Samsa entró" -> "señor Samsa").
    # Empty string means "the span had no proper noun" (verb false positive).
    # Providers that don't compute POS may omit this key; consumers fall back
    # to `text` when it is absent.
    propn: str


class NERProvider(ABC):
    @abstractmethod
    def extract_entities(self, text: str) -> list[Entity]:
        """Return named entities with span offsets."""
