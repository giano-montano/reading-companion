from __future__ import annotations
import logging
from companion.providers.ner_base import Entity, NERProvider

logger = logging.getLogger(__name__)

# Preferred Spanish models in priority order
_ES_FALLBACK_MODELS = ["es_core_news_lg", "es_core_news_md", "es_core_news_sm"]


class SpacyNERProvider(NERProvider):
    """
    Uses a spaCy pipeline for NER.
    Default model targets Spanish; falls back through smaller Spanish models automatically.
    Requires: pip install spacy && python -m spacy download es_core_news_sm
    """

    def __init__(self, model: str = "es_core_news_sm") -> None:
        try:
            import spacy
        except ImportError as exc:
            raise ImportError("pip install spacy") from exc

        self._nlp = self._load_model(spacy, model)

    @staticmethod
    def _load_model(spacy, preferred: str):
        candidates = [preferred] + [m for m in _ES_FALLBACK_MODELS if m != preferred]
        for name in candidates:
            try:
                nlp = spacy.load(name)
                if name != preferred:
                    logger.warning("Loaded spaCy model %r (preferred %r not found).", name, preferred)
                return nlp
            except OSError:
                continue
        tried = ", ".join(candidates)
        raise OSError(
            f"No spaCy model found. Tried: {tried}. "
            f"Install with: python -m spacy download es_core_news_sm"
        )

    def extract_entities(self, text: str) -> list[Entity]:
        doc = self._nlp(text)
        return [
            Entity(text=ent.text, label=ent.label_, start=ent.start_char, end=ent.end_char)
            for ent in doc.ents
        ]
