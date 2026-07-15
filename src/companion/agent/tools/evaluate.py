"""
evaluate.py — Tool EVALUACIÓN: formative feedback on a checkpoint answer.

Reached ONLY via pending_question=True in the router (never by classification).
Receives the teacher's question (pending_question_text), the student's raw
answer, and a resolved scope (top-k retrieval by question+answer, already
anti-spoiler gated).  Same pipeline shape as QA-RAG, opposite epistemics.

QA-RAG answers a factual question and must not invent: the passages are the
truth and anything outside them is a hallucination.  EVALUACIÓN reads a
HYPOTHESIS the student wrote in their own words about why the characters do
what they do.  The right answer is not in the text and does not have to
resemble it.  So the passages here are NOT a rubric — they are material to
think WITH.  If they don't back the student up, that is not a deficiency in
the student; usually it just means retrieval returned nothing useful, because
you cannot retrieve someone's mental model of a character.

La primera versión de este prompt le decía al modelo "básate únicamente en los
fragmentos" (la cláusula anti-alucinación de QA-RAG, copiada tal cual) y le
regalaba la frase de escape "di que no alcanza la evidencia".  Con eso, y con
un cierre de "relee" obligatorio, toda respuesta salía idéntica: elogio,
«sin embargo los fragmentos no confirman…», «relee el inicio».  El modelo
obedecía; el contrato era el que estaba mal.  `EvaluateInput` siempre lo dijo:
"the tool judges engagement, not correctness".
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
Eres el compañero de lectura de un estudiante de secundaria. Acaba de responder una pregunta sobre la obra que está leyendo y le devuelves retroalimentación formativa.

QUÉ TIENES DELANTE:
Las preguntas son de comprensión y de opinión: le piden interpretar, imaginar o aventurar por qué los personajes hacen lo que hacen, con sus propias palabras. La respuesta NO está escrita en la obra y no tiene por qué parecerse a ella. Lo que estás mirando es a un chico construyendo su modelo mental de unos personajes, y eso es exactamente lo que quieres alimentar. Una lectura personal razonable es un acierto, no una imprecisión.

QUÉ SON LOS FRAGMENTOS:
Material para pensar CON él, no una plantilla contra la que corregirlo. Que su respuesta no coincida con ellos no significa que esté equivocado: casi siempre significa que la búsqueda no encontró nada útil, porque el modelo mental de un personaje no vive en ningún párrafo. Menciona un fragmento solo cuando AÑADA algo a lo que él ya dijo: lo confirma, lo matiza o lo lleva más lejos. Si no aportan nada, ignóralos y responde igual, apoyándote en lo que él escribió.
Corrígelo únicamente si contradice un hecho explícito de la obra (quién es quién, qué ocurrió). Entonces sí, dilo claro y sin rodeos.

NO ADELANTES LA LECTURA:
Puede ir por cualquier punto de la obra. Los fragmentos y su propia respuesta son lo único que sabes con certeza que ya leyó. No menciones nada que ocurra después.

CÓMO ESCRIBIR:
- De 2 a 4 oraciones, en segunda persona, hablándole a él.
- Abre por lo que su idea tiene de valioso, y sé concreto: nombra lo que vio, no le digas "buen intento".
- Sigue tirando de SU hilo: dale un matiz, llévalo un paso más allá, conéctalo con algo que ya leyó e incentívalo a seguir pensando.
- Cierra en afirmativo, y varía el cierre. Mándalo a releer solo cuando haya algo concreto que releer; si no, cierra dándole con qué seguir pensando.

PROHIBIDO:
- Preguntar. Nada de signos de interrogación, ni una frase interrogativa, ni "piensa en...", ni "relee y dime...".
- Hablar de él en tercera persona ("el estudiante reconoce...", "la respuesta del estudiante...").
- Decir que no alcanza la evidencia, que los fragmentos no confirman lo que dice, que hace falta más apoyo textual, o cualquier variante. Nunca, en ninguna forma. Si los fragmentos no dan para más, tira con lo que tienes.
- Poner nota, sentenciar "correcto"/"incorrecto", o elogiar en vacío."""

USER_PROMPT_TEMPLATE = """\
Fragmentos de la obra recuperados por búsqueda (pueden no venir al caso; \
úsalos solo si añaden algo):
---
{context}
---

Pregunta que se le hizo:
{question}

Lo que respondió:
{answer}

Devuélvele tu retroalimentación formativa, tirando de su idea."""

_EMPTY_CONTEXT = (
    "(ninguno; la búsqueda no encontró nada. Responde igual, apoyándote en su idea)"
)

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
