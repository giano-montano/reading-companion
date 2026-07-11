"""
AgentRuntime — glue between the intent Router and the concrete tools, emitting
a uniform Server-Sent-Events stream for the chat endpoint.

The API never talks to tools directly: it hands the runtime the student message
plus the frontend-supplied `AgentState`/`ReadingState`, and consumes a sequence
of `(event_name, payload)` pairs.  Every branch of the router maps to events so
the frontend consumes ONE transport model.

Event vocabulary (event_name → payload):
    route      {tool}                         always first
    token      {delta}                        qa_rag: incremental answer text
    citations  {citations, answered, ok}      qa_rag: source spans, terminal
    clarify    {clarification, clarify_count} router asked to rephrase
    image_job  {job_id, poll_url}             imagen: async job handle (phase 3)
    notice     {message, tool}                stub/not-yet-implemented branches
    done       {}                             always last

QA-RAG streaming is SIMULATED for now: the orchestrator produces the full answer
(70B, ~30s) and the runtime slices it into `token` events.  Swapping in real
token streaming later only changes `_stream_qa_rag`, not the event contract.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from companion.agent.orchestrator import QaRagOrchestrator
from companion.agent.router import Router, RouterAction
from companion.agent.state import AgentState
from companion.agent.tools.contracts import ReadingState
from companion.images.runner import start_image_job_thread
from companion.scope.catalog import build_scope_text, get_catalog
from companion.visual_support.schemas import VisualSupportRequest

Event = tuple[str, dict[str, Any]]

# Split preserving trailing whitespace so re-concatenation is loss-free.
_TOKEN_RE = re.compile(r"\S+\s*")

MIN_IMAGE_TEXT_LEN = 20


class AgentRuntime:
    def __init__(self, router: Router, orchestrator: QaRagOrchestrator) -> None:
        self._router = router
        self._orchestrator = orchestrator

    def run(
        self,
        *,
        message: str,
        book_id: str,
        agent_state: AgentState,
        reading_state: ReadingState,
    ) -> Iterator[Event]:
        """Route the message and yield the resulting SSE events."""
        decision = self._router.decide(
            student_text=message,
            pending_question=agent_state.pending_question,
            history=agent_state.history,
            clarify_count=agent_state.clarify_count,
        )

        if decision.action is RouterAction.CLARIFY:
            yield "route", {"tool": "clarify"}
            yield "clarify", {
                "clarification": decision.clarification,
                "clarify_count": decision.clarify_count,
            }
            yield "done", {}
            return

        tool = decision.tool
        yield "route", {"tool": tool}

        if tool == "qa_rag":
            yield from self._stream_qa_rag(
                query=decision.query or message,
                book_id=book_id,
                agent_state=agent_state,
                reading_state=reading_state,
            )
        elif tool == "imagen":
            yield from self._enqueue_image(
                book_id=book_id,
                reading_state=reading_state,
            )
        elif tool == "evaluacion":
            # Deferred: participation-stance grading is not defined yet.
            yield "notice", {
                "tool": "evaluacion",
                "message": "La evaluación de participación aún no está implementada.",
            }
        else:
            # resumir / grafo (and any future label) — not on the MVP path yet.
            yield "notice", {
                "tool": tool,
                "message": f"La herramienta '{tool}' aún no está disponible.",
            }

        yield "done", {}

    # -- branches -----------------------------------------------------------

    def _stream_qa_rag(
        self,
        *,
        query: str,
        book_id: str,
        agent_state: AgentState,
        reading_state: ReadingState,
    ) -> Iterator[Event]:
        output = self._orchestrator.run(
            query=query,
            agent_state=agent_state,
            book_id=book_id,
            reading_state=reading_state,
        )

        for match in _TOKEN_RE.finditer(output.message):
            yield "token", {"delta": match.group(0)}

        yield "citations", {
            "citations": [c.model_dump() for c in output.citations],
            "answered": output.answered,
            "ok": output.ok,
        }

    def _enqueue_image(
        self,
        *,
        book_id: str,
        reading_state: ReadingState,
    ) -> Iterator[Event]:
        """Illustrate what the student currently sees (the visible focus chunks).

        Chat-triggered images always use the 'lo que veo' scope: the frontend's
        `focus_chunk_ids`.  Generation is async — we hand back a job_id and the
        frontend polls `/api/images/{job_id}`."""
        focus_ids = reading_state.focus_chunk_ids
        if not focus_ids:
            yield "notice", {
                "tool": "imagen",
                "message": "No sé qué parte estás viendo ahora mismo para ilustrarla.",
            }
            return

        try:
            chunks = get_catalog(book_id).by_ids(focus_ids)
        except FileNotFoundError:
            yield "notice", {
                "tool": "imagen",
                "message": f"No encuentro el contenido del libro '{book_id}'.",
            }
            return

        text = build_scope_text(chunks)
        if len(text.strip()) < MIN_IMAGE_TEXT_LEN:
            yield "notice", {
                "tool": "imagen",
                "message": "Lo que veo ahora no tiene suficiente texto para ilustrarlo.",
            }
            return

        # scope 'paragraph' → single-panel illustration of the visible fragment.
        vsr = VisualSupportRequest(text=text, scope="paragraph")
        job_id = start_image_job_thread(vsr)
        yield "image_job", {
            "job_id": job_id,
            "poll_url": f"/api/images/{job_id}",
        }
