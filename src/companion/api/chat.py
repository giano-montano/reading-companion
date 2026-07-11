"""
/api/chat — router-driven chat endpoint.

Always responds with `text/event-stream`.  The frontend consumes one SSE stream
regardless of which tool the router picks; the `event:` name discriminates
(see `companion.agent.runtime` for the vocabulary).

The heavy objects (E5 embedder, Chroma, LLMs) come from `api.deps` singletons —
built once per process, never per request.
"""
from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from companion.agent.runtime import AgentRuntime, Event
from companion.agent.state import AgentState
from companion.agent.tools.contracts import ReadingState
from companion.api.deps import get_orchestrator, get_router

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    book_id: str = Field(..., description="Snake-case book id, e.g. 'la_metamorfosis_franz_kafka'.")
    message: str = Field(..., min_length=1, description="Raw student message.")
    agent_state: AgentState = Field(default_factory=AgentState)
    reading_state: ReadingState = Field(default_factory=ReadingState)


def _sse(event: str, data: dict) -> str:
    """Serialize one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _event_stream(events: Iterator[Event]) -> Iterator[str]:
    try:
        for name, payload in events:
            yield _sse(name, payload)
    except Exception as exc:  # never leave the stream hanging on an error
        yield _sse("error", {"message": str(exc)})
        yield _sse("done", {})


@router.post("")
def chat(payload: ChatRequest) -> StreamingResponse:
    runtime = AgentRuntime(router=get_router(), orchestrator=get_orchestrator())
    events = runtime.run(
        message=payload.message,
        book_id=payload.book_id,
        agent_state=payload.agent_state,
        reading_state=payload.reading_state,
    )
    return StreamingResponse(
        _event_stream(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
        },
    )
