"""
Retrieval writer — produce `retrieval.jsonl` with one line per chunk, plus
generated `hypothetical_questions` (5 per chunk by default).

The LLM used is whatever `LLM_PROVIDER` resolves to.  If the configured
provider is "mock" (default), the bundled `MockLLMProvider` returns a
canned JSON array — enough to smoke-test the pipeline without API keys.

Output format mirrors `data/outputs/retrievals/retrievals.md`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from companion.corpus.book_master import BookMaster, BookChunk

logger = logging.getLogger(__name__)

DEFAULT_QUESTIONS_PROMPT_ES = """\
Eres un profesor de literatura preparando material para un alumno de secundaria \
que va a consultar este fragmento de una obra. Devuelve únicamente un array \
JSON con exactamente {n} preguntas en español que un alumno podría hacer y \
que este fragmento ayudaría a responder. Las preguntas deben ser variadas \
(sobre personajes, trama, contexto, inferencia, vocabulario) y naturales \
(como las haría un adolescente, no un crítico).

Fragmento:
\"\"\"
{chunk_text}
\"\"\"

Devuelve únicamente el array JSON, sin texto adicional ni bloques de código."""


class _LLM(Protocol):
    def complete(self, prompt: str) -> str: ...


def _get_llm() -> _LLM:
    """Resolve the content LLM.  Defaults to MockLLMProvider if no API key set."""
    try:
        from companion.providers.factory import get_content_llm
        llm = get_content_llm()
        if llm is not None:
            return llm
    except Exception as exc:
        logger.warning("get_content_llm() failed (%s); falling back to MockLLMProvider.", exc)

    from companion.providers.mock_llm import MockLLMProvider
    return MockLLMProvider()


def _parse_questions(raw: str, n: int) -> list[str]:
    """Best-effort parse of the LLM JSON array; fall back to a trivial split."""
    raw = raw.strip()
    # strip code fences if present
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            questions = [str(x) for x in data if x]
            if questions:
                return questions[:n]
    except json.JSONDecodeError:
        pass
    # Fallback: split on newlines
    parts = [p.strip(" -•\t") for p in raw.splitlines() if p.strip()]
    return parts[:n] if parts else [f"Pregunta {i + 1} sobre el fragmento." for i in range(n)]


def generate_questions_for_chunk(
    chunk: BookChunk, llm: _LLM, n: int = 5, prompt_template: str = DEFAULT_QUESTIONS_PROMPT_ES
) -> list[str]:
    prompt = prompt_template.format(n=n, chunk_text=chunk.text)
    raw = llm.complete(prompt)
    return _parse_questions(raw, n)


def write_retrieval(
    master: BookMaster,
    out_path: str,
    questions_per_chunk: int = 5,
) -> Path:
    llm = _get_llm()
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for chunk in master.chunks:
            try:
                questions = generate_questions_for_chunk(chunk, llm, n=questions_per_chunk)
            except Exception as exc:
                logger.warning("Failed to generate questions for chunk %d (%s); using fallback.", chunk.id, exc)
                questions = [f"Pregunta {i + 1} sobre el fragmento." for i in range(questions_per_chunk)]
            record = {
                "id": chunk.id,
                "text": chunk.text,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "hypothetical_questions": questions,
                "metadata": {
                    "book_id": master.book_id,
                    "section_ids": chunk.section_ids,
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p
