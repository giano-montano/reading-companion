"""
narrative_elements.py — Panel NER: narrative elements per chunk (spaCy-based).

Decision 2026-07-12: NO LLM here.  A local spaCy pipeline is enough for the
panel's purpose — characters and places, "y poco más".  The schema keeps the
richer categories (objetos_simbolos, temas, emociones) so the contract with
the frontend doesn't change, but with this engine they stay empty (the panel
hides empty categories).

Per-chunk extraction is anti-spoiler by construction: each entry only lists
entities from text the student has already reached.

Quality tricks (still no LLM):
  * Spanish spaCy models often mislabel recurring character names as MISC
    ("Grete").  We vote per entity text ACROSS THE WHOLE BOOK: if a surface
    form is ever PER/LOC, every occurrence follows the majority; a recurring
    capitalized proper noun that is never PER/LOC counts as a character (in a
    novel, a name that repeats is almost always a person).
  * One-off MISC entities are dropped as noise.

This module is IO-free so it can be reused at indexing time; the CLI wrapper
lives in `scripts/extract_narrative_elements.py`.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from pydantic import BaseModel, Field

from companion.providers.ner_base import NERProvider

_MAX_ITEMS_PER_LIST = 8
_MAX_ITEM_LEN = 60

# Surface forms that repeat this often without ever being PER/LOC are treated
# as character names the model failed to label (e.g. "Grete" → MISC).
_MIN_RECURRING = 2

_PERSON_LABELS = {"PER", "PERSON"}
_PLACE_LABELS = {"LOC", "GPE", "FAC"}


class ChunkElements(BaseModel):
    """Narrative elements of ONE chunk, as shown in the frontend NER panel.

    With the spaCy engine only personajes/lugares are populated; the other
    categories are kept for contract stability (and a future richer engine).
    """
    chunk_index: int = Field(0)
    personajes: list[str] = Field(default_factory=list)
    lugares: list[str] = Field(default_factory=list)
    objetos_simbolos: list[str] = Field(default_factory=list)
    temas: list[str] = Field(default_factory=list)
    emociones: list[str] = Field(default_factory=list)


def _chunk_index(chunk_id: str) -> int:
    try:
        return int(chunk_id.rsplit("::", 1)[-1])
    except (ValueError, IndexError):
        return 0


# spaCy on literary Spanish routinely tags sentence openers as entities
# ("Especialmente en los primeros tiempos" → PER, "Arrojó" → LOC).  These
# structural filters cut that noise without an LLM.  Some junk will survive —
# acceptable by decision 2026-07-12 ("simple y suficiente").

# A name never STARTS with a connector/adverb/pronoun/preposition.
_CONNECTOR_STARTS = {
    "pero", "ahora", "entonces", "después", "cuando", "mientras", "aunque",
    "apenas", "así", "ya", "no", "ni", "nunca", "nada", "todo", "todavía",
    "también", "tampoco", "quizá", "quizás", "bueno", "claro", "sólo", "solo",
    "solamente", "finalmente", "primero", "luego", "además", "aquí", "allí",
    "ahí", "hoy", "ayer", "mañana", "sin", "con", "por", "para", "al", "en",
    "de", "desde", "hasta", "sobre", "tras", "ante", "entre", "contra",
    "según", "durante", "y", "o", "u", "e", "si", "sí", "que", "qué", "como",
    "cómo", "donde", "dónde", "esto", "esta", "este", "estos", "estas", "eso",
    "esa", "ese", "esos", "esas", "aquel", "aquella", "él", "ella", "ellos",
    "ellas", "yo", "tú", "usted", "ustedes", "nosotros", "se", "su", "sus",
    "lo", "la", "el", "los", "las", "un", "una", "uno", "dos",
    "ciertamente", "especialmente", "naturalmente", "probablemente",
    "aproximadamente", "exactamente", "respirando", "escuchó", "calló",
}

# Leading article is dropped ("El señor Samsa" → "señor Samsa") before checks.
_LEADING_ARTICLES = {"el", "la", "los", "las", "un", "una"}
# Lowercase tokens that may legally start or join a name.
_HONORIFICS = {"señor", "señora", "don", "doña", "doctor", "doctora",
               "san", "santa", "fray", "sor"}
_PARTICLES = {"de", "del", "la", "el", "los", "las", "y", "e", "von", "van", "da"}
# Single title-case tokens with these endings are almost always verbs
# ("Arrojó", "Tanteando", "Habían").  Chosen to not hit common names
# (María/Adrián/Damián survive: 'ía'/'án' are deliberately NOT here).
_VERB_SUFFIXES = ("ó", "ando", "iendo", "yendo", "aron", "ieron", "aban", "ían", "ados")
# Proper nouns that are not narrative elements.
_JUNK = {"dios", "navidad", "nochebuena", "adiós"}


def _is_title(token: str) -> bool:
    return token[:1].isupper()


def _clean(text: str) -> str:
    """Normalize an entity surface form; '' means 'discard as noise'."""
    clean = re.sub(r"\s+", " ", text).strip(" .,;:¡!¿?«»\"'-—")
    if len(clean) > _MAX_ITEM_LEN or not any(ch.isupper() for ch in clean):
        return ""

    tokens = clean.split()
    if len(tokens) > 1 and tokens[0].lower() in _LEADING_ARTICLES:
        tokens = tokens[1:]
        clean = " ".join(tokens)

    if not 1 <= len(tokens) <= 3:
        return ""
    if clean.lower() in _JUNK:
        return ""

    first = tokens[0]
    if first.lower() in _CONNECTOR_STARTS:
        return ""
    if not (_is_title(first) or first.lower() in _HONORIFICS):
        return ""
    for token in tokens[1:]:
        if not (_is_title(token) or token.lower() in _PARTICLES
                or token.lower() in _HONORIFICS):
            return ""

    if len(tokens) == 1:
        if len(first) < 4:  # "Gre" (vocativos truncados) y similares
            return ""
        if _is_title(first) and first.lower().endswith(_VERB_SUFFIXES):
            return ""

    return clean


def _category_for(label: str) -> str | None:
    if label in _PERSON_LABELS:
        return "personajes"
    if label in _PLACE_LABELS:
        return "lugares"
    return None  # MISC/ORG resolved later by the book-level vote


def extract_book_elements(
    chunks: list[tuple[str, str]],
    ner: NERProvider,
) -> dict[str, ChunkElements]:
    """Extract personajes/lugares for every (chunk_id, text) of a book.

    Two passes: collect raw entities per chunk, then resolve each surface
    form with a book-level majority vote (see module docstring)."""
    raw: dict[str, list[tuple[str, str]]] = {}   # chunk_id → [(surface, label)]
    votes: dict[str, Counter] = defaultdict(Counter)
    surfaces: dict[str, str] = {}                 # key → longest surface seen

    for chunk_id, text in chunks:
        found: list[tuple[str, str]] = []
        for ent in ner.extract_entities(text):
            surface = _clean(ent["text"])
            if not surface:
                continue
            key = surface.lower()
            votes[key][ent["label"]] += 1
            if len(surface) > len(surfaces.get(key, "")):
                surfaces[key] = surface
            found.append((key, ent["label"]))
        raw[chunk_id] = found

    def resolve(key: str) -> str | None:
        v = votes[key]
        per = sum(v[label] for label in _PERSON_LABELS)
        place = sum(v[label] for label in _PLACE_LABELS)
        if per or place:
            return "personajes" if per >= place else "lugares"
        if sum(v.values()) >= _MIN_RECURRING:
            return "personajes"  # recurring unlabeled proper noun ≈ character
        return None

    result: dict[str, ChunkElements] = {}
    for chunk_id, found in raw.items():
        personajes: list[str] = []
        lugares: list[str] = []
        seen: set[str] = set()
        for key, _label in found:
            if key in seen:
                continue
            seen.add(key)
            category = resolve(key)
            if category == "personajes" and len(personajes) < _MAX_ITEMS_PER_LIST:
                personajes.append(surfaces[key])
            elif category == "lugares" and len(lugares) < _MAX_ITEMS_PER_LIST:
                lugares.append(surfaces[key])

        result[chunk_id] = ChunkElements(
            chunk_index=_chunk_index(chunk_id),
            personajes=personajes,
            lugares=lugares,
        )
    return result