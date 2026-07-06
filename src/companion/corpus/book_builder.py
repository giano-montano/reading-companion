"""
BookBuilder — orchestrate the full book-preprocessing pipeline.

  EpubBookLoader → NarrativeChunker → master / reader / retrieval.

Sections (pausas pedagógicas) are applied AFTER the master is generated,
via `companion.corpus.sectioner.apply_pauses()`.  The master defaults to
`sections: []` and every `block.section_id = null`; the user or an agent
marks the pause spots and re-runs the sectioner to bake them in.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from companion.chunkers.narrative import NarrativeChunker
from companion.corpus.book_master import BookBlock, BookMaster, BookMetadata, BookSection
from companion.corpus.canonical_text import recompute_offsets
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


def _to_book_blocks(raw) -> list[BookBlock]:
    out: list[BookBlock] = []
    for r in raw:
        out.append(
            BookBlock(
                id=r.id,
                section_id=None,
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
    chunker: NarrativeChunker | None = None,
    questions_per_chunk: int = 5,
) -> BuildResult:
    base = Path(data_dir)
    master_path = base / "master" / f"{book_id}.master.json"
    reader_path = base / "outputs" / "readers" / f"{book_id}.reader.json"
    retrieval_path = base / "outputs" / "retrievals" / f"{book_id}.retrieval.jsonl"
    for p in (master_path, reader_path, retrieval_path):
        p.parent.mkdir(parents=True, exist_ok=True)

    loader = EpubBookLoader(epub_path)
    _header, raw = loader.load()
    logger.info("Loaded %d raw blocks from %s", len(raw), epub_path)

    book_blocks = _to_book_blocks(raw)
    master = BookMaster(
        book_id=book_id,
        metadata=BookMetadata(
            title=title,
            author=author,
            publication_year=year,
            language=language,
        ),
        sections=[],
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
    logger.info("Wrote master    -> %s", master_path)
    logger.info("Wrote reader    -> %s", reader_path)
    logger.info("Wrote retrieval -> %s", retrieval_path)

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
