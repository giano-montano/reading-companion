"""
build_reader_and_retrieval.py — Derive reader + retrieval files from master.json.

Reads data/master/*.master.json and produces:
  data/outputs/reader/<name>.reader.json       — blocks for app rendering
  data/outputs/retrieval/<name>.retrieval.jsonl — chunks for vectorization

Also generates global indexes:
  data/outputs/reader/reader_index.json
  data/outputs/retrieval/retrieval_all.jsonl
  data/outputs/retrieval/retrieval_summary.json
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MASTER_DIR = ROOT / "data" / "master"
READER_DIR = ROOT / "data" / "outputs" / "reader"
RETRIEVAL_DIR = ROOT / "data" / "outputs" / "retrieval"


def validate_block(block: dict, book_id: str) -> list[str]:
    errors = []
    for field in ("id_block", "type", "text", "chunk_id", "char_start", "char_end", "is_narrative"):
        if field == "chunk_id":
            continue  # can be null
        if field == "is_narrative":
            if not isinstance(block.get(field), bool):
                errors.append(f"{book_id}: block missing boolean {field}")
            continue
        if block.get(field) is None and field != "chunk_id":
            errors.append(f"{book_id}: block {block.get('id_block','?')} missing {field}")
    return errors


def validate_chunk(chunk: dict, book_id: str) -> list[str]:
    errors = []
    for field in ("id_chunk", "text", "char_start", "char_end"):
        if chunk.get(field) is None:
            errors.append(f"{book_id}: chunk missing {field}")
    return errors


def build_reader(data: dict) -> dict:
    """Extract reader data from master (blocks only, no chunks)."""
    return {
        "book_id": data["book_id"],
        "metadata": data["metadata"],
        "blocks": data["blocks"],
    }


def build_retrieval_entries(data: dict) -> list[dict]:
    """Build retrieval entries from master chunks."""
    entries = []
    book_id = data["book_id"]
    metadata = data["metadata"]

    for chunk in data.get("chunks", []):
        entry = {
            "id": chunk["id_chunk"],
            "book_id": book_id,
            "chunk_id": chunk["id_chunk"],
            "text": chunk["text"],
            "metadata": {
                "title": metadata.get("title"),
                "author": metadata.get("author"),
                "publication_year": metadata.get("publication_year"),
                "char_start": chunk["char_start"],
                "char_end": chunk["char_end"],
                    "chunk_summary": "",
            },
        }
        entries.append(entry)
    return entries


def main():
    READER_DIR.mkdir(parents=True, exist_ok=True)
    RETRIEVAL_DIR.mkdir(parents=True, exist_ok=True)

    master_files = sorted(MASTER_DIR.glob("*.master.json"))
    print(f"Procesando {len(master_files)} archivos master...\n")

    reader_index_entries = []
    retrieval_all_entries = []
    retrieval_summary_entries = []

    total_blocks = 0
    total_banderas = 0
    total_chunks = 0
    total_reader_files = 0
    total_retrieval_files = 0

    for fp in master_files:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)

        book_id = data["book_id"]
        metadata = data["metadata"]
        blocks = data.get("blocks", [])
        chunks = data.get("chunks", [])

        # ── validation ────────────────────────────────────────────
        has_errors = False
        for b in blocks:
            errs = validate_block(b, book_id)
            for e in errs:
                print(f"  WARN: {e}")
                has_errors = True

        for c in chunks:
            errs = validate_chunk(c, book_id)
            for e in errs:
                print(f"  WARN: {e}")
                has_errors = True

        if has_errors:
            print(f"  SKIP {fp.name} (errores de validación)")
            continue

        # ── reader ────────────────────────────────────────────────
        if not blocks:
            print(f"  WARN: {book_id} — sin bloques, no se genera reader")
        else:
            reader_data = build_reader(data)
            reader_path = READER_DIR / f"{book_id}.reader.json"
            with open(reader_path, "w", encoding="utf-8") as f:
                json.dump(reader_data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            total_reader_files += 1

            narr = sum(1 for b in blocks if b["is_narrative"])
            flags = sum(1 for b in blocks if b.get("type") == "BANDERA")

            reader_index_entries.append({
                "book_id": book_id,
                "title": metadata.get("title"),
                "author": metadata.get("author"),
                "publication_year": metadata.get("publication_year"),
                "reader_path": f"data/outputs/reader/{book_id}.reader.json",
                "total_blocks": len(blocks),
                "total_narrative_blocks": narr,
                "total_non_narrative_blocks": len(blocks) - narr,
                "total_flags": flags,
            })

            total_blocks += len(blocks)
            total_banderas += flags
            print(f"  reader: {reader_path.name} ({len(blocks)} bloques, {flags} banderas)")

        # ── retrieval ─────────────────────────────────────────────
        if not chunks:
            print(f"  WARN: {book_id} — sin chunks, no se genera retrieval")
        else:
            entries = build_retrieval_entries(data)

            retrieval_path = RETRIEVAL_DIR / f"{book_id}.retrieval.jsonl"
            with open(retrieval_path, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            total_retrieval_files += 1

            retrieval_all_entries.extend(entries)

            chunk_chars = [len(c["text"]) for c in chunks]
            retrieval_summary_entries.append({
                "book_id": book_id,
                "title": metadata.get("title"),
                "author": metadata.get("author"),
                "publication_year": metadata.get("publication_year"),
                "retrieval_path": f"data/outputs/retrieval/{book_id}.retrieval.jsonl",
                "total_chunks": len(chunks),
                "min_chunk_chars": min(chunk_chars) if chunk_chars else 0,
                "max_chunk_chars": max(chunk_chars) if chunk_chars else 0,
                "avg_chunk_chars": round(statistics.mean(chunk_chars), 1) if chunk_chars else 0.0,
            })

            total_chunks += len(chunks)
            print(f"  retrieval: {retrieval_path.name} ({len(chunks)} chunks)")

    # ── reader_index.json ─────────────────────────────────────────
    reader_index_path = READER_DIR / "reader_index.json"
    with open(reader_index_path, "w", encoding="utf-8") as f:
        json.dump({"books": reader_index_entries}, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ── retrieval_all.jsonl ───────────────────────────────────────
    retrieval_all_path = RETRIEVAL_DIR / "retrieval_all.jsonl"
    with open(retrieval_all_path, "w", encoding="utf-8") as f:
        for entry in retrieval_all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── retrieval_summary.json ────────────────────────────────────
    retrieval_summary_path = RETRIEVAL_DIR / "retrieval_summary.json"
    with open(retrieval_summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "books": retrieval_summary_entries,
                "total_books": len(retrieval_summary_entries),
                "total_chunks": total_chunks,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")

    # ── console report ────────────────────────────────────────────
    print()
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"  Libros procesados:        {len(master_files)}")
    print(f"  Archivos reader:          {total_reader_files}")
    print(f"  Archivos retrieval:       {total_retrieval_files}")
    print(f"  Total bloques en reader:  {total_blocks}")
    print(f"  Total banderas:           {total_banderas}")
    print(f"  Total chunks retrieval:   {total_chunks}")
    print(f"  reader_index.json:        {reader_index_path}")
    print(f"  retrieval_all.jsonl:      {retrieval_all_path}")
    print(f"  retrieval_summary.json:   {retrieval_summary_path}")


if __name__ == "__main__":
    main()
