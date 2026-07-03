from __future__ import annotations
from companion.providers.llm_base import LLMProvider


class AnthropicLLMProvider(LLMProvider):
    """Calls the Anthropic Messages API.  Requires ANTHROPIC_API_KEY in env."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 512) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError("pip install anthropic") from exc
        from companion.config import settings
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        return self.chat([{"role": "user", "content": prompt}])

    def chat(self, messages: list[dict[str, str]]) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=messages,  # type: ignore[arg-type]
        )
        return response.content[0].text
