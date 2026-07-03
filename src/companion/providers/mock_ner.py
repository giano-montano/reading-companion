from __future__ import annotations
from companion.providers.ner_base import Entity, NERProvider


class MockNERProvider(NERProvider):
    """Returns no entities.  Used when spaCy is unavailable so EntityEnricher degrades gracefully."""

    def extract_entities(self, text: str) -> list[Entity]:
        return []
