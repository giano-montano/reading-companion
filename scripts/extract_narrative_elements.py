"""
extract_narrative_elements.py — Panel NER: annotate a reader with per-chunk
narrative elements (personajes, lugares) using spaCy — NO LLM (decisión
2026-07-12: local, gratis, segundos en vez de minutos).

Reads the book's chunks from data/outputs/retrieval/{book}.retrieval.jsonl,
extracts entities with the spaCy Spanish pipeline (NER_MODEL, with automatic
fallback lg→md→sm), and writes them into
data/outputs/readers/{book}.reader.json as a LAST top-level key:

    "chunk_elements": { "<chunk_id>": {"chunk_index": N, "personajes": [...],
                                       "lugares": [...], ...} }

The reader must already exist (it is Chang's artifact; this script only
appends/replaces the annotation key).  The whole book takes seconds, so each
run recomputes everything — no resume machinery.

Usage:
    python scripts/extract_narrative_elements.py la_metamorfosis_franz_kafka
    python scripts/extract_narrative_elements.py <book_id> --limit 3   # smoke test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from companion.analysis.narrative_elements import extract_book_elements
from companion.config import settings
from companion.providers.spacy_ner import SpacyNERProvider
from companion.scope.catalog import get_catalog

REPO_ROOT = Path(__file__).resolve().parent.parent
READER_DIR = REPO_ROOT / "data" / "outputs" / "readers"


def _save_reader(reader_path: Path, reader: dict, elements: dict) -> None:
    """Write atomically, keeping chunk_elements as the LAST top-level key."""
    reader.pop("chunk_elements", None)
    reader["chunk_elements"] = dict(
        sorted(elements.items(), key=lambda kv: kv[1].get("chunk_index", 0))
    )
    tmp_path = reader_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(reader, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, reader_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("book_id", help="p. ej. la_metamorfosis_franz_kafka")
    parser.add_argument("--limit", type=int, default=0,
                        help="procesar solo los primeros N chunks (smoke test)")
    args = parser.parse_args()

    reader_path = READER_DIR / f"{args.book_id}.reader.json"
    if not reader_path.exists():
        print(f"ERROR: no existe {reader_path} — el reader debe estar creado antes.")
        return 1

    with open(reader_path, encoding="utf-8") as f:
        reader = json.load(f)

    chunks = get_catalog(args.book_id).all()
    if args.limit > 0:
        chunks = chunks[: args.limit]

    print(f"{args.book_id}: {len(chunks)} chunks, modelo spaCy '{settings.ner_model}'")
    t0 = time.time()
    ner = SpacyNERProvider(settings.ner_model)

    elements = {
        chunk_id: result.model_dump()
        for chunk_id, result in extract_book_elements(
            [(c.chunk_id, c.text) for c in chunks], ner
        ).items()
    }

    _save_reader(reader_path, reader, elements)

    n_pers = sum(len(e["personajes"]) for e in elements.values())
    n_lug = sum(len(e["lugares"]) for e in elements.values())
    print(f"Listo: {len(elements)} chunks anotados en {reader_path.name} "
          f"({time.time() - t0:.1f}s) — {n_pers} menciones de personajes, "
          f"{n_lug} de lugares.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
