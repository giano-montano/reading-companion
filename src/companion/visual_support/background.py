"""
background.py — Lo mínimo que el planificador necesita saber y el chunk visible no dice.

Problema real: a media obra el texto dice "no podía darse la vuelta en la cama" y
jamás repite que Gregorio es un insecto (solo 7 de los 96 chunks lo mencionan).  El
8B leía eso y describía a un hombre.  No es un problema de prompt: es que le falta
un dato.

Solución mínima: por cada personaje de la escena (nombres del NER), UNA búsqueda
"cómo es X, su aspecto físico", filtrada por el mismo anti-spoiler del QA-RAG, y se
queda con los pasajes que de verdad describen a alguien.  Dos chunks, y ya.

Sin NER en el reader no hay nombres → no hay trasfondo.  La imagen sale peor, nunca
rota.
"""
from __future__ import annotations

import logging
import re

from companion.scope.catalog import chunk_index, get_characters

logger = logging.getLogger(__name__)

_TOP_K = 15   # el anti-spoiler recorta DESPUÉS; con el top_k del QA-RAG (5) no queda nada
_MAX_CHUNKS = 2
_MAX_NAMES = 2

# Una consulta POR personaje.  Juntar varios nombres en la misma arruina la búsqueda:
# el vector cae "entre" los dos y recupera los pasajes donde coinciden (capítulos
# tardíos) en vez del que describe a uno.  Medido: "cómo es Gregorio Samsa" trae el
# chunk 1 (la transformación); "cómo es Gregorio Samsa, Greta" no lo trae ni en el top 15.
_IDENTITY_QUERY = "Cómo es {name}. Su aspecto físico, su cuerpo, su apariencia."

# La similitud semántica sabe que un chunk "va de Gregorio", pero no distingue el que
# lo DESCRIBE del que solo lo menciona.  Entre los candidatos, nos quedamos con los
# que traen pistas visuales.
_APPEARANCE_RE = re.compile(
    r"\b(cuerpo|cara|rostro|ojos|mirada|cabello|pelo|barba|piel|manos|brazos|piernas|"
    r"patas|espalda|cabeza|vientre|caparaz\w+|alas|figura|estatura|alto|bajo|delgado|"
    r"flaco|gordo|viejo|anciano|joven|vestid\w+|ropa|traje|sombrero|uniforme|aspecto|"
    r"apariencia|convertid\w+|transformad\w+|monstruos\w+|insecto)\b",
    re.I,
)


def _appearance_score(text: str, name: str) -> int:
    """Pistas visuales distintas del pasaje (+ si nombra a ESTE personaje)."""
    score = len({m.group(0).lower() for m in _APPEARANCE_RE.finditer(text)})
    first = name.split()[0].lower() if name else ""
    return score + (2 if first and first in text.lower() else 0)


def build_background(
    *,
    orchestrator,
    book_id: str,
    scene: str,
    focus_ids: list[str],
    max_progress_chunk_index: int,
) -> str:
    """Pasajes ya leídos que describen a los personajes de la escena.  "" si no hay."""
    names = get_characters(book_id, focus_ids)[:_MAX_NAMES]
    if not names:
        return ""

    # El techo nunca baja de lo que el alumno tiene delante: lo que ve, ya lo ha leído.
    ceiling = max(
        max_progress_chunk_index,
        max((chunk_index(cid) for cid in focus_ids), default=0),
    )

    selected: dict[str, str] = {}
    for name in names:
        try:
            hits = orchestrator.retrieve_background(
                query=_IDENTITY_QUERY.format(name=name),
                book_id=book_id,
                max_chunk_index=ceiling,
                exclude=focus_ids,
                top_k=_TOP_K,
            )
        except Exception as exc:  # noqa: BLE001 — degradar, no romper
            logger.warning("no pude recuperar trasfondo (%s): %s", book_id, exc)
            continue

        best = max(hits, key=lambda h: _appearance_score(h.text, name), default=None)
        if best is not None and len(selected) < _MAX_CHUNKS:
            selected.setdefault(best.chunk_id, best.text)

    if not selected:
        return ""

    ordered = sorted(selected.items(), key=lambda kv: chunk_index(kv[0]))
    return "\n\n".join(text.strip() for _, text in ordered)
