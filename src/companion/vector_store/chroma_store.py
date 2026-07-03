from __future__ import annotations
import json
from rag.schemas import EnrichedChunk, RetrievedDoc
from rag.vector_store.base import VectorStore


def _collection_name(variant: str) -> str:
    return f"rag_{variant}"


class ChromaVectorStore(VectorStore):
    """Persistent Chroma collection per variant.  One collection = one experimental condition."""

    def __init__(self, persist_dir: str = "./chroma_db") -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError("pip install chromadb") from exc
        self._client = chromadb.PersistentClient(path=persist_dir)

    def _get_or_create(self, variant: str):
        import chromadb
        return self._client.get_or_create_collection(
            name=_collection_name(variant),
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        chunks: list[EnrichedChunk],
        embeddings: list[list[float]],
        variant: str,
    ) -> None:
        col = self._get_or_create(variant)
        col.add(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=[c.original_text for c in chunks],
            metadatas=[
                {
                    **{k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
                       for k, v in c.metadata.items()},
                    "doc_id": c.doc_id,
                    "enricher_name": c.enricher_name,
                    "embedded_text": c.embedded_text,
                }
                for c in chunks
            ],
        )

    def search(
        self,
        query_embedding: list[float],
        variant: str,
        top_k: int,
    ) -> list[RetrievedDoc]:
        col = self._get_or_create(variant)
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, col.count()),
            include=["documents", "metadatas", "distances"],
        )
        docs: list[RetrievedDoc] = []
        for chunk_id, text, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # Chroma cosine distance: score = 1 - distance
            docs.append(
                RetrievedDoc(
                    chunk_id=chunk_id,
                    text=text,
                    score=round(1.0 - dist, 4),
                    char_start=int(meta.get("char_start", 0)),  # añadir
                    char_end=int(meta.get("char_end", 0)),      # añadir
                    metadata=meta,
                )
            )
        return docs

    def clear(self, variant: str) -> None:
        name = _collection_name(variant)
        try:
            self._client.delete_collection(name)
        except Exception:
            pass

    def collection_exists(self, variant: str) -> bool:
        try:
            col = self._client.get_collection(_collection_name(variant))
            return col.count() > 0
        except Exception:
            return False
