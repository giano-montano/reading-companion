from __future__ import annotations
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Thin wrapper around any LLM backend.  All enrichers and the generator use this."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Single-turn text completion."""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]]) -> str:
        """Multi-turn chat completion.  messages = [{"role": "user"|"assistant", "content": "..."}]"""
