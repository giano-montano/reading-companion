"""
Shared, expensive singletons for the API layer.

The E5 embedder takes ~24s to load and the Chroma client opens a persistent
handle; both MUST be built once per process, never per request.  These helpers
memoize the heavy objects so every request reuses the same instances.

Contract #3 is honored downstream: the router uses `get_router_llm()` (8B) and
QA-RAG uses `get_content_llm()` (70B); they never share a cache instance.
"""
from __future__ import annotations

from functools import lru_cache

from companion.agent.orchestrator import QaRagOrchestrator
from companion.agent.router import Router
from companion.config import settings
from companion.embedders.base import Embedder
from companion.embedders.factory import get_embedder
from companion.providers.factory import get_content_llm, get_router_llm
from companion.vector_store.base import VectorStore
from companion.vector_store.chroma_store import ChromaVectorStore


@lru_cache(maxsize=1)
def get_shared_embedder() -> Embedder:
    """E5 embedder (~24s cold load). Built once, reused across all requests."""
    return get_embedder()


@lru_cache(maxsize=1)
def get_shared_vector_store() -> VectorStore:
    """Persistent Chroma client. One handle per process."""
    return ChromaVectorStore(persist_dir=settings.chroma_persist_dir)


@lru_cache(maxsize=1)
def get_orchestrator() -> QaRagOrchestrator:
    """Full QA-RAG pipeline wired with shared embedder/store + content LLM (70B)."""
    return QaRagOrchestrator(
        embedder=get_shared_embedder(),
        vector_store=get_shared_vector_store(),
        llm=get_content_llm(),
        top_k=settings.top_k,
    )


@lru_cache(maxsize=1)
def get_router() -> Router:
    """Intent router backed by the 8B router LLM (temp 0)."""
    return Router(router_llm=get_router_llm())


def warmup() -> None:
    """Eagerly build the heavy singletons (call at startup to avoid a slow
    first request).  Safe to call multiple times — memoized."""
    get_shared_embedder()
    get_shared_vector_store()
    get_orchestrator()
    get_router()
