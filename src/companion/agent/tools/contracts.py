"""
Tool I/O contracts — the typed boundary between the agent runtime and the four
tools (RESUMIR | QA-RAG | EVALUACIÓN | GRAFO).

Design rules baked into these types:

  * Every tool receives an ALREADY-RESOLVED scope (`list[ScopeChunk]`): the
    ScopeResolver / Retriever decide which chunks are in play, never the tool
    and never the LLM.  A tool never re-queries the vector store.
  * Every tool receives the frontend `ReadingState` as EXPLICIT context.  The
    three reading variables are computed client-side; the LLM never sets them.
  * Anti-spoiler gating (chunks whose index > max_progress_chunk_index are
    dropped) is applied UPSTREAM, before the scope reaches the tool.  By the
    time a tool sees its `scope`, it is already safe.  Tools trust the scope.
  * `ScopeChunk` offsets are absolute over the canonical text and satisfy
    `canonical_text[char_start:char_end] == text`.  Citations reuse those same
    offsets so the frontend can highlight source spans.

DO NOT change field names without updating the router, the ScopeResolver, the
API layer and the frontend — this shape is shared across all of them.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

# Router labels.  Default route (unclassified) is "qa_rag".  "imagen" is a
# routing target only (async illustration job) — it has no ToolInput/ToolOutput
# variant, so it is absent from the discriminated unions below.
ToolName = Literal["resumir", "qa_rag", "evaluacion", "grafo", "imagen"]


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

class ScopeChunk(BaseModel):
    """
    One chunk of the resolved scope handed to a tool.

    Identity is `chunk_id` + absolute offsets; `text` is the canonical slice
    `canonical_text[char_start:char_end]`.  `score` is only set when the scope
    came from the Retriever (QA-RAG); it is None for ScopeResolver output.
    """
    chunk_id: str
    char_start: int = Field(0)   # absolute offset in the canonical text
    char_end: int = Field(0)     # absolute offset in the canonical text
    text: str
    score: float | None = None


class ReadingState(BaseModel):
    """
    Reading position reported by the frontend on EVERY request.  Explicit
    context — the LLM never produces or mutates these values.

      A) focus_chunk_ids          chunks intersecting the viewport right now
      B) max_progress_section     section-level high-water mark (ScopeResolver)
      C) max_progress_chunk_index chunk-based anti-spoiler gate (auto-incremental)

    The anti-spoiler filter uses C (max_progress_chunk_index), NEVER A or B.
    B is used by the ScopeResolver for section-level scoping (hasta_aqui mode).
    """
    focus_chunk_ids: list[str] = Field(default_factory=list)
    max_progress_section: int = Field(0)
    max_progress_chunk_index: int = Field(
        default=0,
        description="Highest chunk index the student has reached. Anti-spoiler gate.",
    )


class Citation(BaseModel):
    """A source span the frontend can highlight in the rendered text."""
    chunk_id: str
    char_start: int = Field(0)
    char_end: int = Field(0)


# ---------------------------------------------------------------------------
# Input contracts
# ---------------------------------------------------------------------------

class ToolInput(BaseModel):
    """Common to all tools: a resolved scope + the frontend reading state."""
    tool: ToolName
    scope: list[ScopeChunk] = Field(default_factory=list)
    reading_state: ReadingState


class SummarizeInput(ToolInput):
    """RESUMIR — summarize what the student currently sees.

    `scope` is the viewport region resolved by the ScopeResolver (no retrieval).
    """
    tool: Literal["resumir"] = "resumir"


class QaRagInput(ToolInput):
    """QA-RAG — answer a question about the work.

    `scope` is the top-k retrieved chunks, already gated to chunks
    <= max_progress_chunk_index.  `query` is the student's raw question.
    `history` carries recent chat turns for conversational context.
    """
    tool: Literal["qa_rag"] = "qa_rag"
    query: str
    history: list[dict[str, str]] = Field(default_factory=list)


class EvaluateInput(ToolInput):
    """EVALUACIÓN — participation stance (NOT correction).

    `scope` is the reference passages for the current section.
    `question` is the comprehension prompt posed; `answer` is the student's
    raw attempt.  The tool judges engagement, not correctness.
    """
    tool: Literal["evaluacion"] = "evaluacion"
    question: str
    answer: str


class GraphInput(ToolInput):
    """GRAFO — query the precomputed character graph (graph.json).

    "safe" view is filtered to sections the student has reached.
    "full" view exposes the whole graph and REQUIRES explicit confirmation
    (`confirmed=True`); without it the tool falls back to the safe view and
    asks to confirm.  `scope` is typically empty — the graph is read from
    graph.json, not chunks.
    """
    tool: Literal["grafo"] = "grafo"
    view: Literal["safe", "full"] = "safe"
    confirmed: bool = False


# ---------------------------------------------------------------------------
# Output contracts
# ---------------------------------------------------------------------------

class ToolOutput(BaseModel):
    """Common to all tools: chat text + source spans for highlighting."""
    tool: ToolName
    ok: bool = True
    message: str                                        # rendered in the chat
    citations: list[Citation] = Field(default_factory=list)


class SummarizeOutput(ToolOutput):
    tool: Literal["resumir"] = "resumir"


class QaRagOutput(ToolOutput):
    tool: Literal["qa_rag"] = "qa_rag"
    # False when nothing relevant exists within the anti-spoiler window.
    answered: bool = True


class EvaluateOutput(ToolOutput):
    tool: Literal["evaluacion"] = "evaluacion"
    # Participation signal: did the student make a genuine attempt?
    attempt_detected: bool = True


class GraphNode(BaseModel):
    id: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    # Section in which this relation first becomes known; used for gating.
    first_section: int = Field(0)


class GraphOutput(ToolOutput):
    tool: Literal["grafo"] = "grafo"
    view: Literal["safe", "full"] = "safe"
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    # True when the safe view hid nodes/edges beyond the student's progress.
    truncated_by_progress: bool = False
    # True when "full" was requested without confirmation → safe view returned.
    requires_confirmation: bool = False


# ---------------------------------------------------------------------------
# Discriminated unions — convenient at the router / API boundary
# ---------------------------------------------------------------------------

ToolInputUnion = Annotated[
    Union[SummarizeInput, QaRagInput, EvaluateInput, GraphInput],
    Field(discriminator="tool"),
]

ToolOutputUnion = Annotated[
    Union[SummarizeOutput, QaRagOutput, EvaluateOutput, GraphOutput],
    Field(discriminator="tool"),
]
