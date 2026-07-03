from __future__ import annotations
from companion.enrichers.base import Enricher
from companion.providers.llm_base import LLMProvider
from companion.schemas import Chunk, EnrichedChunk

# Maximum characters of the parent document passed to the LLM as context.
_DOC_CONTEXT_LIMIT = 3000

SUMMARY_PROMPT_ES = """\
Se te proporciona un fragmento de una obra literaria española y el texto completo \
de la obra como contexto. Escribe 1-2 oraciones en ESPAÑOL que sitúen el fragmento \
dentro de la obra: a qué parte de la historia pertenece, qué personajes aparecen, \
y qué sucede en él. Esta descripción se usará para recuperar el fragmento cuando \
alguien haga preguntas relacionadas.

<obra_contexto>
{doc_context}
</obra_contexto>

<fragmento>
{chunk_text}
</fragmento>

Descripción contextual en español (1-2 oraciones):"""


class SummaryEnricher(Enricher):
    """
    Contextual Retrieval style (Anthropic 2024 / Zhang 2025).
    Generates a 1-2 sentence Spanish context that situates the chunk within its
    source work, then PREPENDS it to the chunk text in embedded_text.

    What goes into embedded_text : "<context summary>\n\n<original chunk text>"
    What goes into metadata      : {"summary": "<context summary>"}
    """

    name = "summary"

    def __init__(self, llm: LLMProvider, prompt_template: str = SUMMARY_PROMPT_ES) -> None:
        self._llm = llm
        self._template = prompt_template

    def enrich(self, chunk: Chunk, doc_text: str = "") -> EnrichedChunk:
        doc_context = doc_text[:_DOC_CONTEXT_LIMIT] if doc_text else chunk.text[:_DOC_CONTEXT_LIMIT]
        prompt = self._template.format(
            doc_context=doc_context,
            chunk_text=chunk.text,
        )
        summary = self._llm.complete(prompt).strip()
        embedded = f"{summary}\n\n{chunk.text}"
        return EnrichedChunk(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            original_text=chunk.text,
            embedded_text=embedded,
            metadata={
                **chunk.metadata,
                "char_start":  chunk.char_start,   # añadir
                "char_end":    chunk.char_end,     # añadir
                "chunk_index": chunk.chunk_index,
                "summary": summary,
            },
            enricher_name=self.name,
        )
