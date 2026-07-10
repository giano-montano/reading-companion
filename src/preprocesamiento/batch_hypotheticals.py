"""
batch_hypotheticals.py — Accepts chunk questions via stdin/stdout batch processing.

Reads questions from a temporary JSON file and merges into the hypotheticals output.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HYPOTHETICALS_DIR = ROOT / "data" / "outputs" / "hypotheticals"


def write_batch(book_id: str, batch: dict[str, list[str]]) -> None:
    """Write a batch of chunk questions, merging with existing file."""
    hpath = HYPOTHETICALS_DIR / f"{book_id}.hypotheticals.jsonl"
    HYPOTHETICALS_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing entries
    existing: dict[str, list[str]] = {}
    if hpath.exists():
        with open(hpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                cid = entry.get("chunk_id", "")
                qs = entry.get("hypothetical_questions", [])
                if cid:
                    existing[cid] = qs

    # Merge new batch
    existing.update(batch)

    # Read retrieval to get chunk order
    retrieval_path = ROOT / "data" / "outputs" / "retrieval" / f"{book_id}.retrieval.jsonl"
    chunk_order: list[str] = []
    with open(retrieval_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            cid = entry.get("chunk_id", "")
            if cid:
                chunk_order.append(cid)

    # Write all in order
    with open(hpath, "w", encoding="utf-8") as f:
        for cid in chunk_order:
            qs = existing.get(cid, [])
            entry = {"chunk_id": cid, "hypothetical_questions": qs}
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    written = sum(1 for cid in chunk_order if cid in existing and len(existing[cid]) == 5)
    print(f"Saved: {written}/{len(chunk_order)} chunks with 5 questions")
    print(f"File: {hpath}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python batch_hypotheticals.py <book_id> <batch_json_file>")
        sys.exit(1)

    book_id = sys.argv[1]
    batch_file = sys.argv[2]

    with open(batch_file, "r", encoding="utf-8") as f:
        batch = json.load(f)

    write_batch(book_id, batch)
