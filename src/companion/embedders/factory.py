from __future__ import annotations
from companion.embedders.base import Embedder
from companion.config import settings


def get_embedder() -> Embedder:
    from companion.embedders.sentence_transformer import SentenceTransformerEmbedder
    return SentenceTransformerEmbedder(model_name=settings.embedding_model)
