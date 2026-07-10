"""
Router — decides WHICH tool handles the student's message.  It never executes
the tool and never resolves scope; it returns a decision + the NL-level args it
can extract from the text.  The orchestrator resolves scope/reading_state and
runs the tool afterwards.

Decision flow (see `Router.decide`):

    pregunta_pendiente == True
        └─► ROUTE → EVALUACIÓN   (answer = student text)   [no LLM call]

    otherwise → classify with the 8B router LLM (temp 0) into
        RESUMIR | QA-RAG | GRAFO | NO_CLASIFICABLE
        ├─ a real tool ─► ROUTE → that tool
        └─ NO_CLASIFICABLE
             ├─ clarify budget left ─► CLARIFY  (re-ask the student, 1–2×)
             └─ budget exhausted    ─► ROUTE → QA-RAG   (default route)

Contract #3: this uses the ROUTER llm only.  It must be a `get_router_llm()`
instance — never the content llm.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from companion.agent.tools.contracts import ToolName
from companion.providers.llm_base import LLMProvider


class RouterAction(str, Enum):
    ROUTE = "route"       # a tool was chosen; execute it downstream
    CLARIFY = "clarify"   # ask the student to rephrase; no tool yet


class DecisionSource(str, Enum):
    PENDING_QUESTION = "pending_question"   # forced to Evaluación
    CLASSIFIER = "classifier"               # 8B picked a tool
    FALLBACK_DEFAULT = "fallback_default"   # unclassifiable → QA-RAG default


class RouterDecision(BaseModel):
    """
    The router's output.  When action is CLARIFY, `tool` is None and
    `clarification` holds the message for the student.  `scope`/`reading_state`
    are intentionally absent — the orchestrator fills those before running.
    """
    action: RouterAction
    tool: ToolName | None = None
    # NL-level args extracted from the message (scope is resolved elsewhere):
    query: str | None = None       # QA-RAG: the student's question
    answer: str | None = None      # EVALUACIÓN: the student's attempt
    # Re-ask the student when unclassifiable and budget remains:
    clarification: str | None = None
    clarify_count: int = 0         # updated count to thread back into AgentState
    # Observability:
    source: DecisionSource | None = None
    raw_label: str | None = None   # what the classifier actually returned


# Classifier label → tool.  EVALUACIÓN is deliberately NOT here: it is reached
# only via pregunta_pendiente, never by classification.
_LABEL_TO_TOOL: dict[str, ToolName] = {
    "RESUMIR": "resumir",
    "QA-RAG": "qa_rag",
    "QA_RAG": "qa_rag",
    "QA": "qa_rag",
    "GRAFO": "grafo",
}
_UNCLASSIFIABLE = "NO_CLASIFICABLE"

_SYSTEM = (
    "Eres un clasificador de intención para un compañero de lectura escolar. "
    "Lee el último mensaje del alumno (con el historial como contexto) y "
    "responde EXACTAMENTE con una sola etiqueta, sin explicación:\n"
    "  RESUMIR          — pide resumir/recapitular lo que está leyendo.\n"
    "  QA-RAG           — hace una pregunta sobre la obra, personajes o trama.\n"
    "  GRAFO            — pide ver el grafo/mapa de relaciones entre personajes.\n"
    "  NO_CLASIFICABLE  — saludo, ruido, o intención imposible de determinar.\n"
    "Responde solo la etiqueta."
)

_CLARIFY_MESSAGES = [
    "No estoy seguro de qué necesitas. ¿Quieres que te resuma lo que estás "
    "leyendo, que responda una pregunta sobre la obra, o que te muestre el "
    "grafo de personajes?",
    "Sigo sin entenderte bien. Dímelo con otras palabras: ¿un resumen, una "
    "pregunta sobre la historia, o el mapa de personajes?",
]


class Router:
    def __init__(self, router_llm: LLMProvider, max_reprompts: int = 2) -> None:
        self._llm = router_llm
        self._max_reprompts = max_reprompts

    def decide(
        self,
        student_text: str,
        pending_question: bool,
        history: list[dict[str, str]] | None = None,
        clarify_count: int = 0,
    ) -> RouterDecision:
        # 1) A question is pending → the message is an answer to evaluate.
        if pending_question:
            return RouterDecision(
                action=RouterAction.ROUTE,
                tool="evaluacion",
                answer=student_text,
                source=DecisionSource.PENDING_QUESTION,
                clarify_count=clarify_count,
            )

        # 2) Classify with the 8B router LLM (temp 0).
        raw = self._classify(student_text, history or [])
        tool = _LABEL_TO_TOOL.get(raw)

        if tool is not None:
            return RouterDecision(
                action=RouterAction.ROUTE,
                tool=tool,
                query=student_text if tool == "qa_rag" else None,
                source=DecisionSource.CLASSIFIER,
                raw_label=raw,
                clarify_count=clarify_count,
            )

        # 3) NO_CLASIFICABLE → re-ask the student while budget remains.
        if clarify_count < self._max_reprompts:
            msg = _CLARIFY_MESSAGES[min(clarify_count, len(_CLARIFY_MESSAGES) - 1)]
            return RouterDecision(
                action=RouterAction.CLARIFY,
                clarification=msg,
                clarify_count=clarify_count + 1,
                source=DecisionSource.CLASSIFIER,
                raw_label=raw,
            )

        # 4) Budget exhausted → default route.
        return RouterDecision(
            action=RouterAction.ROUTE,
            tool="qa_rag",
            query=student_text,
            source=DecisionSource.FALLBACK_DEFAULT,
            raw_label=raw,
            clarify_count=clarify_count,
        )

    # -- internals ----------------------------------------------------------

    def _classify(self, student_text: str, history: list[dict[str, str]]) -> str:
        """Return a normalized label string (e.g. 'QA-RAG' or 'NO_CLASIFICABLE')."""
        prompt = self._build_prompt(student_text, history)
        raw = self._llm.complete(prompt)
        return self._parse_label(raw)

    def _build_prompt(self, student_text: str, history: list[dict[str, str]]) -> str:
        parts = [_SYSTEM, ""]
        if history:
            parts.append("Historial reciente:")
            for turn in history[-6:]:
                role = "Alumno" if turn.get("role") == "user" else "Compañero"
                parts.append(f"{role}: {turn.get('content', '')}")
            parts.append("")
        parts.append(f"Mensaje del alumno: {student_text}")
        parts.append("Etiqueta:")
        return "\n".join(parts)

    def _parse_label(self, raw: str) -> str:
        """Map any model output to a known label; unknown → NO_CLASIFICABLE."""
        up = raw.strip().upper()
        # Exact/contains match against known labels (longest first to avoid
        # 'QA' matching before 'QA-RAG').
        for label in ("RESUMIR", "QA-RAG", "QA_RAG", "GRAFO", _UNCLASSIFIABLE, "QA"):
            if label in up:
                return "QA-RAG" if label in ("QA_RAG", "QA") else label
        return _UNCLASSIFIABLE
