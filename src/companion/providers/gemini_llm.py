"""
Google Gemini provider via google-generativeai SDK.
Only used when LLM_PROVIDER=gemini and GOOGLE_API_KEY is set.
"""
from __future__ import annotations

import logging
import time

from companion.providers.llm_base import LLMProvider

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BACKOFF_BASE = 2.0  # seconds; doubles each attempt


class GeminiProvider(LLMProvider):
    """Calls Gemini Flash (or any configured Gemini model) with exponential-backoff retry."""

    def __init__(self, model: str = "gemini-1.5-flash") -> None:
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError("pip install google-generativeai") from exc
        from companion.config import settings
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is not set in env / .env")
        genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(model)
        self.model_name = model

    def complete(self, prompt: str) -> str:
        return self._retry(lambda: self._model.generate_content(prompt).text)

    def chat(self, messages: list[dict[str, str]]) -> str:
        history = [
            {"role": ("user" if m["role"] == "user" else "model"), "parts": [m["content"]]}
            for m in messages[:-1]
        ]
        last = messages[-1]["content"]
        chat = self._model.start_chat(history=history)
        return self._retry(lambda: chat.send_message(last).text)

    def _retry(self, fn):
        for attempt in range(_MAX_RETRIES):
            try:
                return fn()
            except Exception as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "Gemini error on attempt %d/%d (%s). Retrying in %.1fs…",
                    attempt + 1, _MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
