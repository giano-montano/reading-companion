"""
index_to_chroma.py — Indexa retrieval.jsonl en ChromaDB con preguntas hipotéticas.

Lee data/outputs/retrieval/<book_id>.retrieval.jsonl, construye embedded_text
que incluye las hypothetical_questions concatenadas al texto original, lo
embebe con SentenceTransformer y lo almacena en ChromaDB.

Cada libro se guarda en una colección separada:
  rag_{book_id}

Uso:
  .venv\\Scripts\\python.exe -m preprocesamiento.index_to_chroma --all
  .venv\\Scripts\\python.exe -m preprocesamiento.index_to_chroma --book_id la_metamorfosis_franz_kafka
  .venv\\Scripts\\python.exe -m preprocesamiento.index_to_chroma --list
  .venv\\Scripts\\python.exe -m preprocesamiento.index_to_chroma --all --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RETRIEVAL_DIR = ROOT / "data" / "outputs" / "retrieval"
RETRIEVAL_SUMMARY = RETRIEVAL_DIR / "retrieval_summary.json"


def _build_embedder():
    from companion.embedders.factory import get_embedder
    return get_embedder()


def _build_store():
    from companion.vector_store.chroma_store import ChromaVectorStore
    from companion.config import settings
    return ChromaVectorStore(persist_dir=settings.chroma_persist_dir)


def index_retrieval_file(
    retrieval_path: Path,
    dry_run: bool = False,
    clear_existing: bool = False,
) -> int:
    """Index chunks from a retrieval.jsonl into ChromaDB.

    Returns number of chunks indexed.
    """
    with open(retrieval_path, "r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        return 0

    book_id = entries[0]["book_id"]
    variant = book_id

    # ── build EnrichedChunks with questions in embedded_text ──────────
    from companion.schemas import EnrichedChunk

    enriched = []
    for entry in entries:
        meta = entry.get("metadata", {})
        questions = meta.get("hypothetical_questions", [])
        chunk_text = entry["text"]

        if questions:
            embedded_text = "\n".join(questions) + "\n\n" + chunk_text
        else:
            embedded_text = chunk_text

        enriched.append(
            EnrichedChunk(
                chunk_id=entry["chunk_id"],
                doc_id=book_id,
                original_text=chunk_text,
                embedded_text=embedded_text,
                metadata={
                    "title": meta.get("title", ""),
                    "author": meta.get("author", ""),
                    "publication_year": meta.get("publication_year", ""),
                    "char_start": meta.get("char_start", 0),
                    "char_end": meta.get("char_end", 0),
                    "hypothetical_questions": questions,
                },
                enricher_name="hypothetical_questions",
            )
        )

    if dry_run:
        total_questions = sum(
            len(c.metadata.get("hypothetical_questions", [])) for c in enriched
        )
        print(
            f"  {book_id}: {len(enriched)} chunks, "
            f"{total_questions} preguntas -> coleccion rag_{variant}"
        )
        return len(enriched)

    # ── embed + store ─────────────────────────────────────────────────
    embedder = _build_embedder()
    store = _build_store()

    if clear_existing:
        store.clear(variant)

    texts = [c.embedded_text for c in enriched]
    batch_size = 32
    total = len(enriched)

    for i in range(0, total, batch_size):
        batch_chunks = enriched[i : i + batch_size]
        batch_texts = texts[i : i + batch_size]
        embeddings = embedder.embed_batch(batch_texts)
        store.add(batch_chunks, embeddings, variant=variant)
        progress = min(i + batch_size, total)
        if progress % 64 == 0 or progress == total:
            print(f"    {progress}/{total} chunks")

    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Indexa retrieval.jsonl en ChromaDB con preguntas hipoteticas"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book_id", type=str, help="ID del libro")
    group.add_argument("--all", action="store_true", help="Indexar todos los libros")
    group.add_argument("--list", action="store_true", help="Listar colecciones en ChromaDB")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar sin indexar")
    parser.add_argument(
        "--clear", action="store_true", help="Limpiar coleccion existente antes de indexar"
    )
    args = parser.parse_args()

    if args.list:
        store = _build_store()
        from companion.config import settings
        db_dir = Path(settings.chroma_persist_dir)
        if db_dir.exists():
            subdirs = sorted(
                d.name for d in db_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
            if subdirs:
                print("Colecciones en ChromaDB:")
                for sd in subdirs:
                    try:
                        col = store._client.get_collection(sd)
                        count = col.count()
                        print(f"  {sd}: {count} chunks")
                    except Exception:
                        print(f"  {sd}")
            else:
                print("ChromaDB vacio")
        else:
            print("ChromaDB no inicializado (directorio no existe)")
        return

    if args.all:
        if not RETRIEVAL_SUMMARY.exists():
            print("No se encontro retrieval_summary.json", file=sys.stderr)
            sys.exit(1)
        with open(RETRIEVAL_SUMMARY, "r", encoding="utf-8") as f:
            summary = json.load(f)
        book_ids = [b["book_id"] for b in summary["books"]]
    else:
        book_ids = [args.book_id]

    total_indexed = 0
    for book_id in book_ids:
        rpath = RETRIEVAL_DIR / f"{book_id}.retrieval.jsonl"
        if not rpath.exists():
            print(f"  SKIP: {rpath} no encontrado", file=sys.stderr)
            continue

        n = index_retrieval_file(rpath, dry_run=args.dry_run, clear_existing=args.clear)
        total_indexed += n

    if args.dry_run:
        print(f"\n[dry-run] {total_indexed} chunks serian indexados en {len(book_ids)} colecciones")
    else:
        print(f"\nTotal: {total_indexed} chunks indexados en {len(book_ids)} colecciones")


if __name__ == "__main__":
    main()
