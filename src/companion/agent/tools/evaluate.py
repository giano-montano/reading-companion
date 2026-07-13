"""
evaluate.py — Tool EVALUACIÓN: formative feedback on a checkpoint answer.

Reached ONLY via pending_question=True in the router (never by classification).
Receives the teacher's question (pending_question_text), the student's raw
answer, and a resolved scope (top-k retrieval by question+answer, already
anti-spoiler gated).  Same pipeline shape as QA-RAG, different system prompt:
the goal is formative feedback — acknowledge what the answer gets right, point
at gaps grounded in the passages, invite to re-read — never a grade and never
a bare "incorrecto".
"""
from __future__ import annotations

import re

from companion.agent.tools.contracts import (
    Citation,
    EvaluateInput,
    EvaluateOutput,
    ScopeChunk,
)
from companion.providers.llm_base import LLMProvider

SYSTEM_PROMPT = """\
Eres un companero de lectura para estudiantes de secundaria que estan leyendo \
una obra literaria en espanol. El estudiante acaba de responder una pregunta \
de comprension planteada previamente por un profesor.

Tu tarea es dar retroalimentacion FORMATIVA sobre la respuesta del estudiante, \
basandote UNICAMENTE en los fragmentos de la obra que te proporciono como \
referencia. No es un examen: no pongas nota, no digas "incorrecto" a secas y \
no compares al estudiante con nadie.

Reglas:
- Responde en español, con tono cálido y cercano, adecuado para un adolescente.
- No hagas nuevas preguntas al final, concluye en tu respuesta.
- Empieza reconociendo lo que la respuesta tiene de valido o interesante.
- Si hay vacios o imprecisiones, senalalos con delicadeza apoyandote en los \
fragmentos ("en el texto se menciona que..."), e invita a releer o repensar.
- Si la respuesta es muy corta o no responde la pregunta, animalo a intentarlo \
con sus propias palabras, dandole una pista pequena basada en los fragmentos.
- NO reveles eventos que ocurren mas adelante en la obra (spoilers).
- NO des la respuesta completa de inmediato: guia, no resuelvas.
- Manten tu retroalimentacion entre 2 y 5 oraciones.
- Si no hay fragmentos de referencia, evalua con prudencia solo la relacion \
entre la pregunta y la respuesta, sin inventar detalles de la obra.\
    """

USER_PROMPT_TEMPLATE = """\
Fragmentos de referencia de la obra:
---
{context}
---

Pregunta del profesor:
{question}

Respuesta del estudiante:
{answer}

Da tu retroalimentacion formativa basandote unicamente en los fragmentos \
anteriores."""

_EMPTY_CONTEXT = "(sin fragmentos de referencia disponibles en esta parte de la obra)"

# A "genuine attempt" needs at least a few words; "no se" or an emoji is not
# an attempt.  Heuristic on purpose — the signal is participation, not quality.
_MIN_ATTEMPT_WORDS = 3


def _detect_attempt(answer: str) -> bool:
    words = re.findall(r"\w+", answer, flags=re.UNICODE)
    return len(words) >= _MIN_ATTEMPT_WORDS


def _build_context(chunks: list[ScopeChunk]) -> str:
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[{i}] {chunk.text.strip()}")
    return "\n\n".join(parts)


def _build_citations(chunks: list[ScopeChunk]) -> list[Citation]:
    return [
        Citation(
            chunk_id=c.chunk_id,
            char_start=c.char_start,
            char_end=c.char_end,
        )
        for c in chunks
    ]


class EvaluateTool:
    """Formative feedback on the student's checkpoint answer (content LLM)."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def execute(self, input: EvaluateInput) -> EvaluateOutput:
        attempt = _detect_attempt(input.answer)

        context = _build_context(input.scope) if input.scope else _EMPTY_CONTEXT
        user_prompt = USER_PROMPT_TEMPLATE.format(
            context=context,
            question=input.question.strip(),
            answer=input.answer.strip() or "(respuesta vacia)",
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self._llm.chat(messages)
        except Exception:
            return EvaluateOutput(
                ok=False,
                attempt_detected=attempt,
                message="Lo siento, ocurrio un error al evaluar tu respuesta. Intenta de nuevo.",
                citations=[],
            )

        if not response.strip():
            return EvaluateOutput(
                ok=False,
                attempt_detected=attempt,
                message="Lo siento, no pude generar la retroalimentacion. Intenta de nuevo.",
                citations=[],
            )

        return EvaluateOutput(
            ok=True,
            attempt_detected=attempt,
            message=response.strip(),
            citations=_build_citations(input.scope),
        )
