from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

READER_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs" / "readers"

router = APIRouter(prefix="/api/books", tags=["books"])

MASTER_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "master"
BOOKS_INDEX_PATH = MASTER_DIR / "index_books.json"


def _load_books_index() -> list[dict]:
    if BOOKS_INDEX_PATH.exists():
        with open(BOOKS_INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
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


def _load_reader(book_id: str) -> dict:
    reader_path = READER_DIR / f"{book_id}.reader.json"
    if not reader_path.exists():
        raise HTTPException(status_code=404, detail=f"Reader not found for book '{book_id}'")
    with open(reader_path, encoding="utf-8") as f:
        return json.load(f)


@router.get("")
def list_books() -> list[dict]:
    """Catálogo de libros disponibles con metadatos y conteos."""
    return _load_books_index()


@router.get("/{book_id}/reader")
def get_reader(book_id: str) -> dict:
    """Devuelve el reader completo (bloques con checkpoints) de un libro."""
    return _load_reader(book_id)
