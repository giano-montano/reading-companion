"""
AgentState — conversational state scoped to a single reading session.

Lives in the frontend (browser tab memory); the backend receives a copy on
every request (stateless API).  The LLM never mutates these values.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

MAX_HISTORY_MESSAGES = 10  # 5 user-assistant pairs


class AgentState(BaseModel):
    """Per-session state sent by the frontend with every chat request."""

    history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Ultimas interacciones [{role, content}, ...]. Max 5 pares (10 mensajes).",
    )
    clarify_count: int = Field(
        default=0,
        ge=0,
        description="Veces que el router ha pedido clarificacion en esta sesion.",
    )
    pending_question: bool = Field(
        default=False,
        description="True cuando el sistema espera que el alumno responda una pregunta de evaluacion.",
    )
    pending_question_text: str = Field(
        default="",
        description="Texto de la pregunta de evaluacion pendiente.",
    )

    def trim_history(self) -> AgentState:
        """Return a copy with history truncated to the last N messages."""
        if len(self.history) <= MAX_HISTORY_MESSAGES:
            return self
        return self.model_copy(update={"history": self.history[-MAX_HISTORY_MESSAGES:]})

    def add_turn(self, user_msg: str, assistant_msg: str) -> AgentState:
        """Append a user-assistant pair and trim."""
        new_history = [
            *self.history,
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
        if len(new_history) > MAX_HISTORY_MESSAGES:
            new_history = new_history[-MAX_HISTORY_MESSAGES:]
        return self.model_copy(update={"history": new_history})
