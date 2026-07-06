"""
Offline indexing pipeline:
  load_corpus -> chunk -> enrich(variant) -> embed -> index
"""
from __future__ import annotations
from collections.abc import Iterator

from rich.console import Console
from rich.progress import track

from companion.chunkers.base import Chunker
from companion.corpus.base import CorpusLoader
from companion.embedders.base import Embedder
from companion.enrichers.base import Enricher
from companion.schemas import Document, EnrichedChunk
from companion.vector_store.base import VectorStore

console = Console()
_BATCH_SIZE = 64


def index_book(
    loader: CorpusLoader,
    chunker: Chunker,
    enricher: Enricher,
    embedder: Embedder,
    store: VectorStore,
    force: bool = False,
) -> int:
    """
    Build a vector index for `variant`.  Returns total chunks indexed.
    Skips if the collection already exists unless force=True.
    """
    if not force and store.collection_exists(variant):
        console.print(f"[yellow]Variant '{variant}' already indexed. Use --force to rebuild.[/yellow]")
        return 0

    store.clear(variant)

    documents: list[Document] = list(loader.load())
    console.print(f"Loaded {len(documents)} documents.")

    # Gather all chunk-document pairs to show progress during enrichment
    chunk_doc_pairs = []
    for doc in documents:
        for chunk in chunker.chunk(doc):
            chunk_doc_pairs.append((chunk, doc.text))

    enriched_chunks: list[EnrichedChunk] = []
    for chunk, doc_text in track(
        chunk_doc_pairs,
        description=f"Enriching chunks [{variant}]",
    ):
        enriched_chunks.append(enricher.enrich(chunk, doc_text=doc_text))

    console.print(f"Produced {len(enriched_chunks)} enriched chunks for variant '{variant}'.")


    # Embed and index in batches
    total = 0
    for start in track(
        range(0, len(enriched_chunks), _BATCH_SIZE),
        description=f"Embedding [{variant}]",
    ):
        batch = enriched_chunks[start : start + _BATCH_SIZE]
        texts = [c.embedded_text for c in batch]
        embeddings = embedder.embed_batch(texts)
        store.add(batch, embeddings, variant=variant)
        total += len(batch)

    console.print(f"[green]Indexed {total} chunks for variant '{variant}'.[/green]")
    return total
