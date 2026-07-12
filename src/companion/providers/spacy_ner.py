from __future__ import annotations
import logging
from companion.providers.ner_base import Entity, NERProvider

logger = logging.getLogger(__name__)

# Preferred Spanish models in priority order
_ES_FALLBACK_MODELS = ["es_core_news_lg", "es_core_news_md", "es_core_news_sm"]

# Lowercase common nouns that legally lead a character name; attached to the
# following proper noun so we keep "señor Samsa" vs "señora Samsa" (padre/madre)
# instead of collapsing both to "Samsa".
_HONORIFICS = {
    "señor", "señora", "señorita", "don", "doña", "doctor", "doctora",
    "san", "santa", "fray", "sor", "reina", "rey", "capitán", "conde",
    "condesa", "duque", "duquesa", "profesor", "profesora",
}
# Lowercase tokens that may sit *between* proper nouns of a single name
# ("Ciudad de México", "Ludwig van Beethoven").
_JOINERS = {"de", "del", "la", "las", "los", "y", "von", "van", "da", "di"}


class SpacyNERProvider(NERProvider):
    """
    Uses a spaCy pipeline for NER.
    Default model targets Spanish; falls back through smaller Spanish models automatically.
    Requires: pip install spacy && python -m spacy download es_core_news_sm

    Beyond raw NER, each entity carries a POS-cleaned `propn` surface: spaCy on
    literary Spanish routinely tags sentence-initial verbs as entities ("Había",
    "Quería") and over-extends spans ("Samsa entró").  We keep only the
    proper-noun tokens (with a leading honorific) so those errors disappear
    without an LLM or a heavier model.
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

    @staticmethod
    def _propn_surface(ent, doc) -> str:
        """Trim an entity span to its proper-noun core + leading honorific.

        Returns '' when the span contains no proper noun (a verb/adverb that
        spaCy mislabelled as an entity)."""
        propn_idx = [tok.i for tok in ent if tok.pos_ == "PROPN"]
        if not propn_idx:
            return ""

        first, last = propn_idx[0], propn_idx[-1]
        core = [
            doc[i].text
            for i in range(first, last + 1)
            if doc[i].pos_ == "PROPN" or doc[i].lower_ in _JOINERS
        ]

        # Honorific immediately before the first proper noun (may sit just
        # outside the entity span, e.g. spaCy returned "Samsa" for "señor Samsa").
        prefix = []
        if first - 1 >= 0 and doc[first - 1].lower_ in _HONORIFICS:
            prefix = [doc[first - 1].text]

        return " ".join(prefix + core).strip()

    def extract_entities(self, text: str) -> list[Entity]:
        doc = self._nlp(text)
        return [
            Entity(
                text=ent.text,
                label=ent.label_,
                start=ent.start_char,
                end=ent.end_char,
                propn=self._propn_surface(ent, doc),
            )
            for ent in doc.ents
        ]
