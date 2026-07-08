"""Generate data/master/index_books.json from all master files."""
from __future__ import annotations

import json
from pathlib import Path

MASTER_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "master"


def build_index() -> list[dict]:
    books = []
    for fp in sorted(MASTER_DIR.glob("*.master.json")):
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)

        blocks = data["blocks"]
        narr = sum(1 for b in blocks if b["is_narrative"])
        banderas = sum(1 for b in blocks if b["type"] == "BANDERA")

        books.append({
            "book_id": data["book_id"],
            "title": data["metadata"]["title"],
            "author": data["metadata"]["author"],
            "publication_year": data["metadata"].get("publication_year"),
            "total_blocks": len(blocks),
            "narrative_blocks": narr,
            "non_narrative_blocks": len(blocks) - narr,
            "banderas": banderas,
        })

    return books


def main():
    books = build_index()
    out_path = MASTER_DIR / "index_books.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Índice generado: {out_path}")
    print(f"Libros: {len(books)}")
    for b in books:
        print(f"  {b['book_id']} — {b['title']} ({b['author']})")


if __name__ == "__main__":
    main()

