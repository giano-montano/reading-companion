"""
Persistent disk cache for LLM calls.
Keyed by SHA-256 of (provider_tag, kind, content) so re-running an experiment
never re-calls the LLM for already-seen prompts.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from companion.providers.llm_base import LLMProvider

logger = logging.getLogger(__name__)


class CachingLLMProvider(LLMProvider):
    """
    Wraps any LLMProvider with a simple file-system cache.
    Cache layout:  <cache_dir>/<first-2-hex>/<sha256>.json
    """

    def __init__(
        self,
        provider: LLMProvider,
        cache_dir: str = "./.llm_cache",
        provider_tag: str = "",
    ) -> None:
        self._provider = provider
        self._root = Path(cache_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._tag = provider_tag or type(provider).__name__

    # ------------------------------------------------------------------
    def complete(self, prompt: str) -> str:
        key = self._key("complete", prompt)
        cached = self._load(key)
        if cached is not None:
            logger.debug("LLM cache hit  [%s…]", key[:8])
            return cached
        result = self._provider.complete(prompt)
        self._save(key, result)
        return result

    def chat(self, messages: list[dict[str, str]]) -> str:
        key = self._key("chat", json.dumps(messages, ensure_ascii=False))
        cached = self._load(key)
        if cached is not None:
            logger.debug("LLM cache hit  [%s…]", key[:8])
            return cached
        result = self._provider.chat(messages)
        self._save(key, result)
        return result

    # ------------------------------------------------------------------
    def _key(self, kind: str, content: str) -> str:
        raw = f"{self._tag}\x00{kind}\x00{content}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        sub = self._root / key[:2]
        sub.mkdir(exist_ok=True)
        return sub / f"{key}.json"

    def _load(self, key: str) -> str | None:
        p = self._path(key)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))["response"]
            except Exception:
                p.unlink(missing_ok=True)
        return None

    def _save(self, key: str, response: str) -> None:
        self._path(key).write_text(
            json.dumps({"response": response}, ensure_ascii=False), encoding="utf-8"
        )
