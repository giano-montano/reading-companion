"""
narrative_elements.py — Panel NER: narrative elements per chunk (spaCy-based).

Decision 2026-07-12: NO LLM here.  A local spaCy pipeline is enough for the
panel's purpose — characters and places, "y poco más".  The schema keeps the
richer categories (objetos_simbolos, temas, emociones) so the contract with
the frontend doesn't change, but with this engine they stay empty (the panel
hides empty categories).

Per-chunk extraction is anti-spoiler by construction: each entry only lists
entities from text the student has already reached.

Quality strategy (plan `research/ner-plan-mejora.md`, 2026-07-12):
  * The heavy lifting is upstream: `SpacyNERProvider` already trims each span
    to its proper-noun core using POS (`Entity.propn`), which kills verb
    false positives ("Había", "Quería") and over-extended spans.  Here we
    just consume that cleaned surface.
  * Only PER and LOC survive (native labels).  MISC/ORG are not rescued.
  * A surface form must appear at least twice in the book to count; one-off
    detections are almost always noise.  Precision over recall, per Giano:
    "prefiero que agarre menos cosas pero que tengan sentido".
  * Alias canonicalization at book level: "Gregorio" ⊂ "Gregorio Samsa" is
    shown as the fuller name, while a shared surname ("Samsa", used by padre,
    madre y Gregorio) stays standalone so "señor Samsa"/"señora Samsa" remain
    distinct.

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
_MAX_TOKENS = 4

# A surface form must be detected at least this many times across the book to
# count; one-off detections are almost always spaCy noise on literary text.
_MIN_MENTIONS = 2

_PERSON_LABELS = {"PER", "PERSON"}
_PLACE_LABELS = {"LOC", "GPE", "FAC"}

# Proper nouns that are not narrative elements worth listing.
_JUNK = {"dios", "navidad", "nochebuena", "adiós"}


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


def _surface(ent) -> str:
    """The cleaned surface for an entity: the provider's POS-trimmed `propn`
    when present (even if empty → discard), else the raw text (legacy/mocks)."""
    propn = ent.get("propn")
    raw = propn if propn is not None else ent.get("text", "")
    clean = re.sub(r"\s+", " ", raw).strip(" .,;:¡!¿?«»\"'-—")
    if not clean or len(clean) > _MAX_ITEM_LEN or len(clean.split()) > _MAX_TOKENS:
        return ""
    if clean.lower() in _JUNK or not any(ch.isupper() for ch in clean):
        return ""
    return clean


def _canonical_personajes(
    emit_keys: set[str],
    inventory_keys: set[str],
    surfaces: dict[str, str],
) -> dict[str, str]:
    """Map each emitted personaje key to its display surface, folding a bare
    first name into the fullest form that starts with it.

    `inventory_keys` may include fuller names too rare to emit on their own
    (e.g. "gregorio samsa" seen once): they still lend their surface as the
    canonical display for the frequent bare "gregorio".  A token that is the
    LAST word of two or more names is a shared surname and stays standalone."""
    tokens = {k: k.split() for k in inventory_keys}
    last_token_count: Counter = Counter()
    first_token_multi: dict[str, list[str]] = defaultdict(list)
    for k in inventory_keys:
        toks = tokens[k]
        if len(toks) > 1:
            last_token_count[toks[-1]] += 1
            first_token_multi[toks[0]].append(k)

    merged: dict[str, str] = {}          # single key -> fuller key
    for k in emit_keys:
        toks = k.split()
        if len(toks) != 1:
            continue
        tok = toks[0]
        if last_token_count[tok] >= 2:
            continue                     # shared surname -> keep standalone
        candidates = first_token_multi.get(tok, [])
        if len(candidates) == 1:
            merged[k] = candidates[0]    # bare first name -> full name

    # Truncation repair ("Gregori" -> "Gregorio"): a single token that is a
    # strict prefix (>=5 chars) of another name's leading token.
    for k in emit_keys:
        if k in merged or len(k.split()) != 1:
            continue
        for other in inventory_keys:
            lead = tokens[other][0]
            if lead != k and len(k) >= 5 and lead.startswith(k):
                merged[k] = other
                break

    def resolve_chain(k: str) -> str:
        seen: set[str] = set()
        while k in merged and k not in seen:
            seen.add(k)
            k = merged[k]
        return k

    return {k: surfaces[resolve_chain(k)] for k in emit_keys}


def extract_book_elements(
    chunks: list[tuple[str, str]],
    ner: NERProvider,
) -> dict[str, ChunkElements]:
    """Extract personajes/lugares for every (chunk_id, text) of a book.

    Two passes: collect cleaned entities per chunk, then resolve each surface
    form using its native PER/LOC labels, book-wide recurrence and alias
    canonicalization (see module docstring)."""
    raw: dict[str, list[str]] = {}                # chunk_id -> [key, ...]
    votes: dict[str, Counter] = defaultdict(Counter)
    surfaces: dict[str, str] = {}                 # key -> longest surface seen

    for chunk_id, text in chunks:
        keys: list[str] = []
        for ent in ner.extract_entities(text):
            surface = _surface(ent)
            if not surface:
                continue
            key = surface.lower()
            votes[key][ent["label"]] += 1
            if len(surface) > len(surfaces.get(key, "")):
                surfaces[key] = surface
            keys.append(key)
        raw[chunk_id] = keys

    def resolve(key: str) -> str | None:
        v = votes[key]
        per = sum(v[label] for label in _PERSON_LABELS)
        place = sum(v[label] for label in _PLACE_LABELS)
        if per == 0 and place == 0:
            return None                  # never a native PER/LOC -> not rescued
        if sum(v.values()) < _MIN_MENTIONS:
            return None                  # one-off -> likely a spaCy slip
        return "personajes" if per >= place else "lugares"

    emit_personajes = {k for k in votes if resolve(k) == "personajes"}
    # Inventory for alias display: every person-ish surface, even rare ones.
    person_inventory = {
        k for k in surfaces
        if sum(votes[k][l] for l in _PERSON_LABELS) >= sum(votes[k][l] for l in _PLACE_LABELS)
        and sum(votes[k][l] for l in _PERSON_LABELS) > 0
    } | emit_personajes
    canon = _canonical_personajes(emit_personajes, person_inventory, surfaces)

    result: dict[str, ChunkElements] = {}
    for chunk_id, keys in raw.items():
        personajes: list[str] = []
        lugares: list[str] = []
        seen: set[str] = set()
        for key in keys:
            category = resolve(key)
            display = canon.get(key) if category == "personajes" else surfaces.get(key)
            if not display or display in seen:
                continue
            if category == "personajes" and len(personajes) < _MAX_ITEMS_PER_LIST:
                seen.add(display)
                personajes.append(display)
            elif category == "lugares" and len(lugares) < _MAX_ITEMS_PER_LIST:
                seen.add(display)
                lugares.append(display)

        result[chunk_id] = ChunkElements(
            chunk_index=_chunk_index(chunk_id),
            personajes=personajes,
            lugares=lugares,
        )
    return result
