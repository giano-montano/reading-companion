from __future__ import annotations
from companion.vector_store.base import VectorStore
from companion.config import settings


def get_vector_store() -> VectorStore:
    if settings.vector_store == "chroma":
        from companion.vector_store.chroma_store import ChromaVectorStore
        return ChromaVectorStore(persist_dir=settings.chroma_persist_dir)
    raise ValueError(f"Unknown vector store: {settings.vector_store!r}")
