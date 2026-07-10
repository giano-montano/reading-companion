"""
orchestrator.py — Full QA-RAG pipeline for answering student questions.

Connects query → embedding → ChromaDB retrieval → anti-spoiler filtering →
ScopeChunk conversion → QaRagTool execution → QaRagOutput.

This is the single entry point called by the API endpoint and the agent runtime.
"""
from __future__ import annotations

from companion.agent.state import AgentState
from companion.agent.tools.contracts import (
    QaRagInput,
    QaRagOutput,
    ReadingState,
    ScopeChunk,
)
from companion.agent.tools.qa_rag import QaRagTool
from companion.config import settings
from companion.embedders.base import Embedder
from companion.providers.llm_base import LLMProvider
from companion.vector_store.base import VectorStore


def _extract_chunk_index(chunk_id: str) -> int:
    """Extract the auto-incremental numeric index from a chunk_id string."""
    try:
        return int(chunk_id.rsplit("::", 1)[-1])
    except (ValueError, IndexError):
        return 0


def _anti_spoiler_filter(
    docs: list,
    max_chunk_index: int,
) -> list:
    """Drop chunks whose index exceeds the student's max progress."""
    if max_chunk_index <= 0:
        return docs  # no gate when progress is unknown (beginning of book)
    return [d for d in docs if _extract_chunk_index(d.chunk_id) <= max_chunk_index]


def _retrieved_to_scope_chunk(doc) -> ScopeChunk:
    """Convert a RetrievedDoc to a ScopeChunk."""
    return ScopeChunk(
        chunk_id=doc.chunk_id,
        char_start=doc.char_start,
        char_end=doc.char_end,
        text=doc.text,
        score=doc.score,
    )


class QaRagOrchestrator:
    """Full QA-RAG pipeline: retrieval → anti-spoiler → generation.

    Usage:
        orchestrator = QaRagOrchestrator(embedder, vector_store, llm)
        output = orchestrator.run(
            query="¿Por qué los padres del muchacho no lo dejaban pescar?",
            agent_state=agent_state,
            book_id="el_viejo_y_el_mar_ernest_hemingway",
            reading_state=reading_state,
        )
    """

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        llm: LLMProvider,
        top_k: int | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = vector_store
        self._tool = QaRagTool(llm=llm)
        self._top_k = top_k or settings.top_k

    def run(
        self,
        query: str,
        agent_state: AgentState,
        book_id: str,
        reading_state: ReadingState,
    ) -> QaRagOutput:
        """Execute the full QA-RAG pipeline.

        Args:
            query: The student's question.
            agent_state: Chat history + session flags.
            book_id: Which book to search (used as ChromaDB variant).
            reading_state: Anti-spoiler gate parameters.

        Returns:
            QaRagOutput with answer, citations, and flags.
        """
        # ── 1. embed + retrieve ──────────────────────────────────────
        query_vec = self._embedder.embed(query)
        retrieved = self._store.search(
            query_vec,
            variant=book_id,
            top_k=self._top_k,
        )

        if not retrieved:
            return QaRagOutput(
                ok=True,
                answered=False,
                message="No encontre fragmentos relevantes en esta parte de la obra.",
                citations=[],
            )

        # ── 2. anti-spoiler gate ─────────────────────────────────────
        max_idx = reading_state.max_progress_chunk_index
        filtered = _anti_spoiler_filter(retrieved, max_idx)

        if not filtered:
            return QaRagOutput(
                ok=True,
                answered=False,
                message="No tengo suficiente contexto en esta parte de la obra para responder eso.",
                citations=[],
            )

        # ── 3. convert to ScopeChunk ─────────────────────────────────
        scope = [_retrieved_to_scope_chunk(d) for d in filtered]

        # ── 4. execute tool ──────────────────────────────────────────
        trimmed_state = agent_state.trim_history()
        tool_input = QaRagInput(
            query=query,
            scope=scope,
            reading_state=reading_state,
            history=trimmed_state.history,
        )

        return self._tool.execute(tool_input)
