"""
BookBuilder — orchestrate the full book-preprocessing pipeline.

  EpubBookLoader → CheckpointResolver (optional) → assign section_ids →
  [NarrativeChunker] → master / reader / retrieval.

Output layout (flat, no per-book folder; see `data/estructura.md`):

  <data_dir>/
    master/<book_id>.master.json
    outputs/readers/<book_id>/reader.json
    outputs/retrievals/<book_id>/retrieval.jsonl

Sections (pausas pedagógicas) are MANUAL by default.  Pass
`--checkpoints=none` (default) to produce a master with all
`blocks[].section_id = null` and `sections: []`.  Use `--checkpoints=json`
with a hand-curated `checkpoints.json` to mark pausas; the heuristic
resolver exists for exploration only and emits a warning.

The entrypoint is `build_book(...)`; see `companion/cli/preprocess.py` for
the CLI wrapper.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from companion.chunkers.narrative import NarrativeChunker
from companion.corpus.book_master import BookBlock, BookMaster, BookMetadata, BookSection
from companion.corpus.canonical_text import recompute_offsets
from companion.corpus.checkpoints import (
    CheckpointResolver,
    assign_section_ids,
)
from companion.corpus.epub_loader import EpubBookLoader
from companion.corpus.master_writer import write_book_master
from companion.corpus.reader_writer import write_reader
from companion.corpus.retrieval_writer import write_retrieval

logger = logging.getLogger(__name__)


@dataclass
class BuildResult:
    book_id: str
    master_path: Path
    reader_path: Path
    retrieval_path: Path
    n_blocks: int
    n_narrative_blocks: int
    n_sections: int
    n_chunks: int


def _to_book_blocks(raw, section_map: dict[int, int | None]) -> list[BookBlock]:
    out: list[BookBlock] = []
    for r in raw:
        out.append(
            BookBlock(
                id=r.id,
                section_id=section_map.get(r.id),
                content=r.content,
                text=r.text,
                chunk_id=None,
                is_narrative=r.is_narrative,
                token_count=_count(r.text),
            )
        )
    return out


def _count(text: str) -> int:
    return int(round(len(text.split()) * 1.3))


def build_book(
    *,
    epub_path: str,
    book_id: str,
    data_dir: str = "data",
    title: str,
    author: str,
    year: int | None = None,
    language: str | None = None,
    checkpoints: CheckpointResolver | None = None,
    chunker: NarrativeChunker | None = None,
    questions_per_chunk: int = 5,
) -> BuildResult:
    base = Path(data_dir)
    master_path = base / "master" / f"{book_id}.master.json"
    reader_path = base / "outputs" / "readers" / book_id / "reader.json"
    retrieval_path = base / "outputs" / "retrievals" / book_id / "retrieval.jsonl"
    for p in (master_path, reader_path, retrieval_path):
        p.parent.mkdir(parents=True, exist_ok=True)

    loader = EpubBookLoader(epub_path)
    _header, raw = loader.load()
    logger.info("Loaded %d raw blocks from %s", len(raw), epub_path)

    if checkpoints is not None:
        plans = checkpoints.resolve(raw)
        section_pairs = assign_section_ids(raw, plans)
        section_map = {bid: sid for bid, sid in section_pairs}
        used = {sid for sid in section_map.values() if sid is not None}
        section_ids: list[int] = sorted(used)
        logger.info("Applied %d manual sections.", len(section_ids))
    else:
        section_map = {b.id: None for b in raw}
        section_ids = []
        logger.info("No checkpoint resolver; all sections will be null.")

    book_blocks = _to_book_blocks(raw, section_map)
    master = BookMaster(
        book_id=book_id,
        metadata=BookMetadata(
            title=title,
            author=author,
            publication_year=year,
            language=language,
        ),
        sections=[BookSection(id=sid) for sid in section_ids],
        blocks=book_blocks,
        chunks=[],
    )

    chunker = chunker or NarrativeChunker()
    master = chunker.chunk(master)
    master = recompute_offsets(master)
    logger.info(
        "Produced %d chunks (target tokens %d).",
        len(master.chunks),
        chunker.params.target_tokens,
    )

    write_book_master(master, str(master_path))
    write_reader(master, str(reader_path))
    write_retrieval(
        master,
        str(retrieval_path),
        questions_per_chunk=questions_per_chunk,
    )
    logger.info("Wrote master    → %s", master_path)
    logger.info("Wrote reader    → %s", reader_path)
    logger.info("Wrote retrieval → %s", retrieval_path)

    return BuildResult(
        book_id=book_id,
        master_path=master_path,
        reader_path=reader_path,
        retrieval_path=retrieval_path,
        n_blocks=len(master.blocks),
        n_narrative_blocks=sum(1 for b in master.blocks if b.is_narrative),
        n_sections=len(master.sections),
        n_chunks=len(master.chunks),
    )
