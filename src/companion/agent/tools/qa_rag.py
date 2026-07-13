"""
qa_rag.py — Tool QA-RAG: answer a student question using retrieved chunks.

Receives a resolved scope (top-k chunks already filtered by anti-spoiler),
chat history, and the student query.  Builds a structured prompt, calls the
content LLM (70B), and returns a QaRagOutput with answer and citations.
"""
from __future__ import annotations

from companion.agent.tools.contracts import Citation, QaRagInput, QaRagOutput, ScopeChunk
from companion.providers.llm_base import LLMProvider

SYSTEM_PROMPT = """\
Eres un asistente de lectura para estudiantes de secundaria que estan leyendo \
una obra literaria en espanol.

Tu tarea es responder preguntas del estudiante basandote UNICAMENTE en los \
fragmentos de la obra que te proporciono como contexto. No inventes informacion \
que no aparezca en esos fragmentos. También puedes aclarar significados de palabras o frases según tu conocimiento general del idioma español, pero no inventes detalles de la obra.

Reglas:
- Responde en espanol, con un tono claro y adecuado para un estudiante.
- Si los fragmentos contienen la respuesta, explicala con tus propias palabras.
- Si los fragmentos NO contienen suficiente informacion para responder, dilo \
honestamente: "No tengo suficiente contexto en esta parte de la obra para \
responder eso."
- NO reveles eventos que ocurren mas adelante en la obra (spoilers).
- Cita los fragmentos que uses indicando su contenido relevante.
- Manten tus respuestas entre 2 y 5 oraciones, salvo que la pregunta requiera \
mas detalle.
- Si el estudiante pregunta algo que no tiene relacion con la obra, responde \
amablemente que solo puedes hablar sobre la lectura."""

USER_PROMPT_TEMPLATE = """\
Fragmentos relevantes de la obra:
---
{context}
---

Pregunta del estudiante:
{query}

Responde basandote unicamente en los fragmentos anteriores."""


def _build_context(chunks: list[ScopeChunk]) -> str:
    """Format retrieved chunks as a numbered context block."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[{i}] {chunk.text.strip()}")
    return "\n\n".join(parts)


def _build_citations(chunks: list[ScopeChunk]) -> list[Citation]:
    """Build citation list from scope chunks."""
    return [
        Citation(
            chunk_id=c.chunk_id,
            char_start=c.char_start,
            char_end=c.char_end,
        )
        for c in chunks
    ]


def _extract_chunk_index(chunk_id: str) -> int:
    """Extract the auto-incremental numeric index from a chunk_id."""
    try:
        return int(chunk_id.rsplit("::", 1)[-1])
    except (ValueError, IndexError):
        return 0


class QaRagTool:
    """Answers student questions using retrieved chunks + content LLM."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def execute(self, input: QaRagInput) -> QaRagOutput:
        scope = input.scope

        if not scope:
            return QaRagOutput(
                ok=True,
                answered=False,
                message="No tengo suficiente contexto en esta parte de la obra para responder eso.",
                citations=[],
            )

        # ── build messages ──────────────────────────────────────────
        user_prompt = USER_PROMPT_TEMPLATE.format(
            context=_build_context(scope),
            query=input.query,
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # Inject recent history (up to last 5 turns)
        if input.history:
            trimmed = input.history[-10:]  # max 5 user-assistant pairs
            messages.extend(trimmed)

        messages.append({"role": "user", "content": user_prompt})

        # ── call LLM ─────────────────────────────────────────────────
        try:
            response = self._llm.chat(messages)
        except Exception:
            return QaRagOutput(
                ok=False,
                answered=False,
                message="Lo siento, ocurrio un error al procesar tu pregunta. Intenta de nuevo.",
                citations=[],
            )

        if not response.strip():
            return QaRagOutput(
                ok=True,
                answered=False,
                message="No tengo suficiente contexto en esta parte de la obra para responder eso.",
                citations=[],
            )

        # ── build output ─────────────────────────────────────────────
        citations = _build_citations(scope)
        return QaRagOutput(
            ok=True,
            answered=True,
            message=response.strip(),
            citations=citations,
        )
