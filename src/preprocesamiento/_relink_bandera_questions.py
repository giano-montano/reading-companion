"""Relink BANDERA questions after block ID changes from rebuild_reader_blocks.

Strategy: match by sequential position within each book.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
READER_DIR = ROOT / "data" / "outputs" / "readers"

# Backup of questions keyed by old bandera IDs (before rebuild)
# We extract them from add_questions_to_banderas.py
from preprocesamiento.add_questions_to_banderas import QUESTIONS as OLD_QUESTIONS


def relink() -> None:
    for rp in sorted(READER_DIR.glob("*.reader.json")):
        data = json.loads(rp.read_text(encoding="utf-8"))
        book_id = data["book_id"]

        # Get banderas in order
        banderas = [b for b in data["blocks"] if b["type"] == "BANDERA"]

        # Build old-to-new mapping: match by the text or just by position
        # Since old bandera IDs were sequential within each book,
        # we can match by the suffix number pattern.
        # Old banderas for this book: {book_id}::block::{N}
        old_banderas = [
            bid for bid in OLD_QUESTIONS
            if bid.startswith(book_id)
        ]
        # Sort by block number
        old_banderas.sort(key=lambda x: int(x.rsplit("::", 2)[-1]))

        # Map old questions to new banderas by position
        for i, bandera in enumerate(banderas):
            if i < len(old_banderas) and old_banderas[i] in OLD_QUESTIONS:
                bandera["questions"] = OLD_QUESTIONS[old_banderas[i]]
            else:
                bandera["questions"] = None

        with open(rp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

        with_q = sum(1 for b in banderas if b.get("questions") and len(b["questions"]) > 0)
        print(f"  {rp.name}: {with_q}/{len(banderas)} banderas with questions")


if __name__ == "__main__":
    relink()
