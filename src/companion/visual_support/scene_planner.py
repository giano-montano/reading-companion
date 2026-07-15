"""
scene_planner.py — Paso previo al generador de imágenes (decisión 2026-07-12).

Problema: el extracto de texto que llega (a veces la obra entera) se volcaba
crudo en el prompt de Flux, y encima se le pedía al modelo de difusión que
"eligiera los momentos visualmente importantes". Un difusor no hace comprensión
lectora: alucina y termina renderizando texto dentro de la imagen.

Solución: un LLM ligero (8B) destila el extracto en
  * `visual_events`  — descripciones de escena concretas, en INGLÉS (el encoder
    de Flux está entrenado en inglés), una por panel, en orden cronológico.
  * `characters`     — rasgos físicos breves, para que el personaje se vea igual
    en los tres paneles y Flux no le invente uno distinto en cada frame.

El prompt de imagen no recibe prosa en absoluto: solo estas escenas ya destiladas
(ver `prompt_builder`, que las monta como un pie de foto corto).

Textos largos → **map-reduce**: se resume cada trozo por separado (en paralelo)
y luego se consolidan esos resúmenes en el plan final. Así una obra entera cabe
sin perder el desenlace.

Si el planner falla, el caller sigue adelante sin plan: la imagen se genera
igual (peor encuadrada, pero nunca se rompe la petición).
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from companion.providers.llm_base import LLMProvider
from companion.visual_support.schemas import VisualCharacter

logger = logging.getLogger(__name__)

# Por encima de esto no mandamos el texto de una sola vez: map-reduce.
_SINGLE_PASS_MAX_CHARS = 6_000
_MAP_CHUNK_CHARS = 4_000
# Tope de llamadas del paso "map" (NIM se satura): si hay más trozos, se
# muestrean uniformemente para conservar inicio, medio y final.
_MAX_MAP_CHUNKS = 10
_MAX_WORKERS = 4
_MAX_CHARACTERS = 4


class ScenePlan(BaseModel):
    visual_events: list[str] = Field(default_factory=list)
    characters: list[VisualCharacter] = Field(default_factory=list)


_PLAN_SYSTEM = """\
You plan illustrations for an educational reading companion used by Spanish
secondary-school students. You read a fragment of a literary work (in Spanish)
and turn it into visual scene descriptions for a text-to-image model.

Reply with STRICT JSON only. No markdown, no code fences, no commentary:
{"visual_events": ["..."], "characters": [{"name": "...", "description": "..."}]}

Rules for `visual_events`:
- Write them in ENGLISH, even though the source is Spanish.
- Exactly the number of events requested, in chronological order.
- ONE sentence each, max ~25 words, purely VISUAL and concrete: who is present,
  where they are, what action is visible.
- Describe only what a viewer could SEE. No inner thoughts, no abstractions, no
  metaphors, no dialogue.
- Use ONLY what the fragment supports. Never invent events, places or characters.
- Never mention words, letters, signs, captions, books with readable titles or
  any writing — the illustration must contain no text.

Rules for `characters`:
- Only characters that actually appear in the events you wrote.
- `description` = brief PHYSICAL appearance (age, build, hair, clothing) so the
  illustrator draws them the same way in every panel. Max ~12 words.
- If the fragment doesn't describe appearance, give a short neutral description
  consistent with the setting and period. Do not invent plot.

Rules for the `Background` section, when it is present:
- It comes from EARLIER passages the student has already read. It is CONTEXT, not
  content: it tells you WHO the characters are and WHAT THEY LOOK LIKE.
- NEVER turn the background into a visual_event. Draw only the `Fragment`.
- Its physical descriptions OVERRIDE your assumptions. If the background reveals a
  character's true form — a transformation, a disguise, a non-human body — the
  `characters` description MUST reflect it, even if the fragment never repeats it.
  A fragment saying "he could not turn over in bed" is a giant insect struggling
  on its back if the background says he woke up transformed into one.
"""

_PLAN_USER = """\
{title_line}Number of visual_events required: {frame_count}
{scope_line}{context_block}
Fragment (THIS is what you must illustrate):
\"\"\"
{text}
\"\"\"

Return the JSON now."""

_CONTEXT_BLOCK = """
Background — earlier passages the student has ALREADY read. Context only: use it to
know who the characters are and what they physically look like. Do NOT illustrate it.
\"\"\"
{context}
\"\"\"
"""

# El trasfondo es apoyo, no el sujeto: da para los 2 chunks que manda
# `background.build_background` (~1.700 chars cada uno).
_MAX_CONTEXT_CHARS = 3_600

_FULL_TEXT_HINT = (
    "This fragment covers a whole work: the events must summarize (1) the "
    "beginning, (2) the central conflict or turning point, and (3) the final "
    "outcome. Do not try to include every event."
)

_MAP_SYSTEM = """\
You condense a fragment of a Spanish literary work into visual facts for an
illustrator. Reply in ENGLISH with 2-3 short sentences describing ONLY what
could be seen: which characters are present, the setting, and the key visible
actions. No interpretation, no dialogue, no quotes, no commentary."""


def _extract_json(raw: str) -> dict:
    text = re.sub(r"```(?:json)?", "", raw).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"respuesta sin JSON: {raw[:200]!r}")
    return json.loads(text[start : end + 1])


def _split_chunks(text: str, size: int, max_chunks: int) -> list[str]:
    """Trocea por párrafos sin partir frases a la mitad; si salen demasiados
    trozos, muestrea uniformemente para conservar inicio, medio y final."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] or [text]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 1 > size:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)

    # Un párrafo gigantesco (texto sin saltos) se parte a lo bruto.
    split: list[str] = []
    for chunk in chunks:
        if len(chunk) <= size * 1.5:
            split.append(chunk)
        else:
            split.extend(chunk[i : i + size] for i in range(0, len(chunk), size))

    if len(split) > max_chunks:
        step = len(split) / max_chunks
        split = [split[int(i * step)] for i in range(max_chunks)]
    return split


class ScenePlanner:
    """Destila un extracto en escenas listas para el generador de imágenes."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def plan(
        self,
        *,
        text: str,
        scope: str,
        frame_count: int,
        title: str | None = None,
        context: str = "",
    ) -> ScenePlan:
        source = text.strip()
        if len(source) > _SINGLE_PASS_MAX_CHARS:
            source = self._condense(source)

        background = context.strip()[:_MAX_CONTEXT_CHARS]
        messages = [
            {"role": "system", "content": _PLAN_SYSTEM},
            {
                "role": "user",
                "content": _PLAN_USER.format(
                    title_line=f"Title: {title}\n" if title else "",
                    frame_count=frame_count,
                    scope_line=_FULL_TEXT_HINT if scope == "full_text" else "",
                    context_block=_CONTEXT_BLOCK.format(context=background) if background else "",
                    text=source,
                ),
            },
        ]
        plan = ScenePlan.model_validate(_extract_json(self._llm.chat(messages)))

        events = [e.strip() for e in plan.visual_events if e and e.strip()][:frame_count]
        if len(events) < frame_count:
            raise ValueError(
                f"el planner devolvió {len(events)} escenas, se pedían {frame_count}"
            )
        return ScenePlan(visual_events=events, characters=plan.characters[:_MAX_CHARACTERS])

    def _condense(self, text: str) -> str:
        """Map-reduce: resume cada trozo y devuelve el digest concatenado."""
        chunks = _split_chunks(text, _MAP_CHUNK_CHARS, _MAX_MAP_CHUNKS)
        logger.info("scene_planner: map-reduce sobre %d trozos", len(chunks))

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            summaries = list(pool.map(self._summarize_chunk, chunks))

        digest = "\n".join(s for s in summaries if s)
        if not digest:
            raise ValueError("map-reduce no produjo ningún resumen")
        return digest

    def _summarize_chunk(self, chunk: str) -> str:
        try:
            return self._llm.chat(
                [
                    {"role": "system", "content": _MAP_SYSTEM},
                    {"role": "user", "content": chunk},
                ]
            ).strip()
        except Exception as exc:  # noqa: BLE001 — un trozo perdido no aborta el plan
            logger.warning("scene_planner: falló el resumen de un trozo: %s", exc)
            return ""
