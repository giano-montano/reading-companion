import logging
import time
from companion.providers.llm_base import LLMProvider

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_BACKOFF_BASE = 2.0  # seconds; doubles each attempt

class NvidiaLLMProvider(LLMProvider):
    """Llama a modelos de NVIDIA NIM utilizando la API compatible con OpenAI."""

    def __init__(self, model: str = "deepseek-ai/deepseek-v4-flash", temperature: float = 0.2) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        
        from companion.config import settings
        if not settings.nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY no está configurada en el entorno / .env")
            
        self._client = OpenAI(
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key,
        )
        self.model = model
        self._temperature = temperature

    def complete(self, prompt: str) -> str:
        return self._retry(
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self._temperature,
                max_tokens=1024,
            ).choices[0].message.content or ""
        )

    def chat(self, messages: list[dict[str, str]]) -> str:
        return self._retry(
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self._temperature,
                max_tokens=1024,
            ).choices[0].message.content or ""
        )

    def _retry(self, fn):
        for attempt in range(_MAX_RETRIES):
            try:
                return fn()
            except Exception as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "NVIDIA API error on attempt %d/%d (%s). Retrying in %.1fs…",
                    attempt + 1, _MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
