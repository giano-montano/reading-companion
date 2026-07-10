"""Preview chunks from retrieval.jsonl for manual qa generation."""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RETRIEVAL_DIR = ROOT / "data" / "outputs" / "retrieval"

def main():
    book_id = sys.argv[1] if len(sys.argv) > 1 else "viaje_al_centro_de_la_tierra_julio_verne"
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    rpath = RETRIEVAL_DIR / f"{book_id}.retrieval.jsonl"
    with open(rpath, "r", encoding="utf-8-sig") as f:
        chunks = [json.loads(line) for line in f if line.strip()]

    for i in range(start, min(start + count, len(chunks))):
        c = chunks[i]
        print(f"=== CHUNK {i+1}: {c['chunk_id']} ===")
        text = c["text"].encode("utf-8", errors="replace").decode("utf-8")
        sys.stdout.buffer.write((text + "\n\n---END---\n\n").encode("utf-8"))
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
