"""
ChunkCatalog — deterministic chunk lookup for scope resolution (no embeddings).

Source of truth is the per-book `retrieval.jsonl` (already produced by the
preprocessing pipeline): every line carries `chunk_id`, `text`, and absolute
`char_start`/`char_end` in metadata.  The catalog translates any frontend
selector into an ordered list of chunks, so tools always receive chunks.

It is aligned to Chang's anti-spoiler axis: the chunk index is the integer
suffix of `book::chunk::N`, and `up_to_index` mirrors the QA-RAG gate.

Used by the image feature to turn "lo que veo / esta sección / hasta el máximo /
toda la obra" into the text that grounds the illustration.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

RETRIEVAL_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data" / "outputs" / "retrieval"
)


def chunk_index(chunk_id: str) -> int:
    """Integer reading-order index from a 'book::chunk::N' id (0 if unparseable)."""
    try:
        return int(chunk_id.rsplit("::", 1)[-1])
    except (ValueError, IndexError):
        return 0


class CatalogChunk(BaseModel):
    chunk_id: str
    index: int
    char_start: int = Field(0)
    char_end: int = Field(0)
    text: str


class ChunkCatalog:
    """Ordered, in-memory index of one book's chunks."""

    def __init__(self, chunks: list[CatalogChunk]) -> None:
        self._chunks = sorted(chunks, key=lambda c: c.index)
        self._by_id = {c.chunk_id: c for c in self._chunks}

    # -- selectors ----------------------------------------------------------

    def by_ids(self, chunk_ids: list[str]) -> list[CatalogChunk]:
        """Chunks matching the given ids, returned in reading order.

        Unknown ids are silently skipped (the frontend may send stale ids)."""
        wanted = {cid for cid in chunk_ids}
        return [c for c in self._chunks if c.chunk_id in wanted]

    def up_to_index(self, max_index: int) -> list[CatalogChunk]:
        """Chunks with index <= max_index (the 'hasta el máximo' window)."""
        return [c for c in self._chunks if c.index <= max_index]

    def all(self) -> list[CatalogChunk]:
        return list(self._chunks)

    def __len__(self) -> int:
        return len(self._chunks)


def _load_catalog(book_id: str) -> ChunkCatalog:
    path = RETRIEVAL_DIR / f"{book_id}.retrieval.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No retrieval file for book '{book_id}': {path}")

    chunks: list[CatalogChunk] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            meta = row.get("metadata", {})
            chunk_id = row["chunk_id"]
            chunks.append(
                CatalogChunk(
                    chunk_id=chunk_id,
                    index=chunk_index(chunk_id),
                    char_start=int(meta.get("char_start", 0)),
                    char_end=int(meta.get("char_end", 0)),
                    text=row.get("text", ""),
                )
            )
    return ChunkCatalog(chunks)


@lru_cache(maxsize=16)
def get_catalog(book_id: str) -> ChunkCatalog:
    """Cached per-book catalog (parsed once, reused across requests)."""
    return _load_catalog(book_id)


READER_DIR = RETRIEVAL_DIR.parent / "readers"


@lru_cache(maxsize=8)
def _chunk_elements(book_id: str) -> dict[str, list[str]]:
    """Personajes por chunk según el NER (`chunk_elements` del reader).

    Devuelve {} cuando el reader no está anotado — es un artefacto OPCIONAL: lo
    escribe `scripts/extract_narrative_elements.py` y se pierde cada vez que se
    regenera el reader.  Sin él las ilustraciones salen peor (peor trasfondo),
    nunca rotas.
    """
    path = READER_DIR / f"{book_id}.reader.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        elements = json.load(f).get("chunk_elements") or {}
    return {
        chunk_id: [p for p in (data.get("personajes") or []) if p]
        for chunk_id, data in elements.items()
    }


def get_characters(book_id: str, chunk_ids: list[str]) -> list[str]:
    """Nombres canónicos de los personajes presentes en esos chunks, sin repetir
    y en orden de aparición.  Lista vacía si el reader no tiene NER.

    El NER da el nombre COMPLETO ("Gregorio Samsa"), y eso importa: buscar por
    "Gregorio" a secas no recupera el pasaje de la transformación; con el nombre
    canónico, sí.
    """
    per_chunk = _chunk_elements(book_id)
    if not per_chunk:
        return []

    seen: dict[str, None] = {}
    for chunk_id in sorted(chunk_ids, key=chunk_index):
        for name in per_chunk.get(chunk_id, []):
            seen.setdefault(name, None)
    return list(seen)


_BOOKS_INDEX = RETRIEVAL_DIR.parent.parent / "master" / "index_books.json"


@lru_cache(maxsize=1)
def _titles() -> dict[str, str]:
    if not _BOOKS_INDEX.exists():
        return {}
    with open(_BOOKS_INDEX, encoding="utf-8") as f:
        return {b["book_id"]: b.get("title", "") for b in json.load(f)}


def get_book_title(book_id: str) -> str | None:
    """Título de la obra, para dar contexto al planificador de escenas.  None si
    no está en el índice (no es motivo para no ilustrar)."""
    return _titles().get(book_id) or None


def build_scope_text(chunks: list[CatalogChunk], max_chars: int = 24_000) -> str:
    """Texto de un scope para ilustrarlo, acotado a `max_chars`.

    Cuando no cabe entero se muestrean chunks COMPLETOS repartidos por toda la
    obra (principio, medio y final).  Antes se truncaba CADA chunk a unos pocos
    cientos de caracteres, y el planificador recibía confeti: "Cuando Gregorio
    Samsa se despertó una mañana despu" + corte.  Frases partidas por la mitad no
    se pueden ilustrar.

    El presupuesto es holgado a propósito: por encima de 6.000 caracteres el
    planificador hace map-reduce (scene_planner), que es justo para esto y ya está
    acotado a 10 llamadas.
    """
    if not chunks:
        return ""

    joined = "\n\n".join(c.text.strip() for c in chunks)
    if len(joined) <= max_chars:
        return joined

    average = max(1, len(joined) // len(chunks))
    keep = max(1, max_chars // average)          # cuántos chunks enteros caben
    step = max(1, -(-len(chunks) // keep))       # ceil: repartidos por la obra
    sampled = [c.text.strip() for c in chunks[::step]][:keep]
    return "\n\n".join(sampled)
