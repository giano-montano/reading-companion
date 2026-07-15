"""
Proveedor de OpenAI.  Mismo contrato que el resto (`LLMProvider`): complete + chat.

Se adapta solo a las manías del modelo.  Los modelos de razonamiento ("mini",
serie o-*, gpt-5*) rechazan con 400 lo que los modelos clásicos aceptan sin
rechistar:

  - `max_tokens`   → exigen `max_completion_tokens`
  - `temperature`  → solo admiten el valor por defecto (1); cualquier otro, 400

En vez de mantener a mano una lista de qué modelo acepta qué (frágil: cambia con
cada release), mandamos la petición y, si la API se queja de un parámetro, lo
corregimos y reintentamos.  La lección se guarda en la instancia, así que el
peaje de la 400 se paga una sola vez por proceso.
"""
from __future__ import annotations

import logging
import time

from companion.providers.llm_base import LLMProvider

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_BACKOFF_BASE = 2.0  # segundos; se dobla en cada intento

# Igual que en NVIDIA: el default del cliente OpenAI son 600s y un request colgado
# nos bloquea 10 minutos.  Cortar y reintentar sale más barato.
_REQUEST_TIMEOUT = 90.0

_MAX_OUTPUT_TOKENS = 1024
# Los modelos de razonamiento gastan tokens *invisibles* pensando antes de
# escribir: si el tope es bajo se lo comen entero razonando y devuelven "".
# Cuando descubrimos que el modelo razona (nos pide max_completion_tokens),
# subimos el techo para dejar sitio a la respuesta.
_MAX_OUTPUT_TOKENS_REASONING = 4096


class OpenAILLMProvider(LLMProvider):
    """Llama a la API de OpenAI (o a cualquier endpoint compatible)."""

    def __init__(
        self,
        model: str = "gpt-5.4-mini",
        temperature: float = 0.2,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc

        from companion.config import settings

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY no está configurada en el entorno / .env")

        self._client = OpenAI(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            timeout=timeout,
        )
        self.model = model
        self._temperature = temperature

        # Lo que creemos que el modelo acepta.  Se corrige solo al primer 400.
        self._token_param = "max_tokens"
        self._max_output_tokens = _MAX_OUTPUT_TOKENS
        self._send_temperature = True

    # -- API pública ---------------------------------------------------------

    def complete(self, prompt: str) -> str:
        return self.chat([{"role": "user", "content": prompt}])

    def chat(self, messages: list[dict[str, str]]) -> str:
        return self._retry(lambda: self._create(messages))

    # -- internals -----------------------------------------------------------

    def _create(self, messages: list[dict[str, str]]) -> str:
        """Una llamada, adaptando los parámetros si el modelo los rechaza."""
        for _ in range(3):  # como mucho una corrección por parámetro conflictivo
            kwargs: dict = {
                "model": self.model,
                "messages": messages,
                self._token_param: self._max_output_tokens,
            }
            if self._send_temperature:
                kwargs["temperature"] = self._temperature

            try:
                response = self._client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001 — miramos si es una 400 corregible
                if not self._adapt_to(exc):
                    raise
                continue  # parámetro corregido: reintenta ya, sin backoff

            return response.choices[0].message.content or ""

        raise RuntimeError(
            f"'{self.model}' sigue rechazando los parámetros tras adaptarlos. "
            "Revisa el modelo en GET /v1/models."
        )

    def _adapt_to(self, exc: Exception) -> bool:
        """¿Es un 400 por un parámetro no soportado? Si sí, se corrige y devuelve True."""
        message = str(exc).lower()
        if "400" not in message and "unsupported" not in message and "invalid" not in message:
            return False

        # 'max_tokens' no vale: este modelo razona → usa max_completion_tokens y
        # sube el techo (el razonamiento consume tokens antes de responder).
        if "max_tokens" in message and self._token_param == "max_tokens":
            self._token_param = "max_completion_tokens"
            self._max_output_tokens = _MAX_OUTPUT_TOKENS_REASONING
            logger.info(
                "%s: es un modelo de razonamiento → max_completion_tokens=%d",
                self.model, self._max_output_tokens,
            )
            return True

        # 'temperature' no vale: el modelo solo admite su valor por defecto.
        # OJO: el router pierde su temperature=0 y deja de ser determinista.
        if "temperature" in message and self._send_temperature:
            self._send_temperature = False
            logger.warning(
                "%s no admite temperature=%.1f; se usará la del modelo. "
                "El router pierde determinismo.",
                self.model, self._temperature,
            )
            return True

        return False

    def _retry(self, fn):
        for attempt in range(_MAX_RETRIES):
            try:
                return fn()
            except Exception as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "OpenAI API error on attempt %d/%d (%s). Retrying in %.1fs…",
                    attempt + 1, _MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
