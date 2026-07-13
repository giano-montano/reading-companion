import logging
import time
from companion.providers.llm_base import LLMProvider

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_BACKOFF_BASE = 2.0  # seconds; doubles each attempt

# El default del cliente OpenAI es 600s: cuando NIM se satura deja requests
# COLGADOS esos 10 minutos (medido: 719s y 1403s por chunk en el script NER).
# Cortar a los 90s y reintentar sale mucho más barato que esperar.
_REQUEST_TIMEOUT = 90.0

class NvidiaLLMProvider(LLMProvider):
    """Llama a modelos de NVIDIA NIM utilizando la API compatible con OpenAI."""

    def __init__(
        self,
        model: str = "deepseek-ai/deepseek-v4-flash",
        temperature: float = 0.2,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> None:
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
            timeout=timeout,
        )
        self.model = model
        self._temperature = temperature

    def complete(self, prompt: str) -> str:
        messages = self._with_reasoning_off([{"role": "user", "content": prompt}])
        return self._retry(
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self._temperature,
                max_tokens=1024,
            ).choices[0].message.content or ""
        )

    def chat(self, messages: list[dict[str, str]]) -> str:
        messages = self._with_reasoning_off(messages)
        return self._retry(
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self._temperature,
                max_tokens=1024,
            ).choices[0].message.content or ""
        )

    def _with_reasoning_off(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Nemotron models reason by default, which doubles/triples latency
        (medido: 27s vs 10s en el mismo prompt). '/no_think' en el system
        prompt lo desactiva; para otros modelos no se toca nada."""
        if "nemotron" not in self.model.lower():
            return messages
        if messages and messages[0].get("role") == "system":
            first = {**messages[0], "content": "/no_think\n" + messages[0]["content"]}
            return [first, *messages[1:]]
        return [{"role": "system", "content": "/no_think"}, *messages]

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
