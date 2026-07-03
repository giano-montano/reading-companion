from __future__ import annotations
from companion.embedders.base import Embedder
from companion.retrieval.reranker import PassthroughReranker, Reranker
from companion.schemas import RetrievedDoc
from companion.vector_store.base import VectorStore


class Retriever:
    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        top_k: int = 5,
        reranker: Reranker | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self.top_k = top_k
        self._reranker = reranker or PassthroughReranker()

    def retrieve(self, query: str, variant: str) -> list[RetrievedDoc]:
        q_vec = self._embedder.embed(query)
        docs = self._store.search(q_vec, variant=variant, top_k=self.top_k)
        return self._reranker.rerank(query, docs)
