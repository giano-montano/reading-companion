"""
BookBuilder — orchestrate the full book-preprocessing pipeline.

  EpubBookLoader → [optional block splitting] → CheckpointResolver →
  assign section_ids → [optional NarrativeChunker] → master/reader/retrieval.

The entrypoint is `build_book(...)`; see `companion/cli/preprocess.py` for
the CLI wrapper.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from companion.chunkers.narrative import NarrativeChunker
from companion.corpus.block_splitting import split_block_at
from companion.corpus.book_master import BookBlock, BookMaster, BookMetadata, BookSection
from companion.corpus.canonical_text import recompute_offsets
from companion.corpus.checkpoints import (
    CheckpointResolver,
    HeuristicCheckpointResolver,
    SectionPlan,
    assign_section_ids,
)
from companion.corpus.epub_loader import EpubBookLoader, RawBlock
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


def _renumber(blocks: list[RawBlock]) -> list[RawBlock]:
    """Re-assign sequential ids after splitting."""
    for i, b in enumerate(blocks, start=1):
        b.id = i
    return blocks


def _next_plan_start(plans: list[SectionPlan], current: SectionPlan) -> int:
    """Return the start_block_id of the next plan, or +inf for the last."""
    later = [p.start_block_id for p in plans if p.id > current.id]
    return min(later) if later else 10**9


def _to_book_blocks(raw: list[RawBlock], section_map: dict[int, int | None]) -> list[BookBlock]:
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


def _apply_block_splits(blocks: list[RawBlock], split_block_ids: set[int]) -> list[RawBlock]:
    """
    If a checkpoint is inside a block (caller tells us which block_ids have a
    checkpoint at position 0 — i.e. the section starts with a non-narrative
    block and the next narrative block must be split), split the narrative
    block at the first sentence after the requested point.

    For the MVP, we use a simpler heuristic: if the first block of a section
    is a header that follows a narrative block in the *previous* section,
    we don't need to split.  We only split when a section start coincides
    with the middle of a `<p>`, which is rare in our EPUBs and we mark
    via `split_block_ids` (computed heuristically by the BookBuilder).
    """
    out: list[RawBlock] = []
    for b in blocks:
        if b.id in split_block_ids and b.is_narrative:
            # split halfway through, as a fallback
            half = max(1, len(b.text) // 2)
            res = split_block_at(b, half)
            if res is not None:
                out.append(res.before)
                # keep second half with same id; renumber will reassign
                out.append(RawBlock(
                    id=b.id,
                    content=res.after.content,
                    text=res.after.text,
                    is_narrative=res.after.is_narrative,
                ))
                continue
        out.append(b)
    return _renumber(out)


def build_book(
    *,
    epub_path: str,
    book_id: str,
    out_dir: str,
    title: str,
    author: str,
    year: int | None = None,
    language: str | None = None,
    checkpoints: CheckpointResolver | None = None,
    split_blocks: bool = True,
    chunker: NarrativeChunker | None = None,
    questions_per_chunk: int = 5,
) -> BuildResult:
    out = Path(out_dir)
    pre_dir = out / "preprocessing"
    reader_dir = out / "prepared" / "reader"
    retrieval_dir = out / "prepared" / "retrieval"
    pre_dir.mkdir(parents=True, exist_ok=True)
    reader_dir.mkdir(parents=True, exist_ok=True)
    retrieval_dir.mkdir(parents=True, exist_ok=True)

    loader = EpubBookLoader(epub_path)
    _header, raw = loader.load()
    logger.info("Loaded %d raw blocks from %s", len(raw), epub_path)

    if split_blocks:
        # MVP heuristic: detect blocks whose text starts with a section header
        # by mistake.  Our EPUBs keep sections intact, so this is a no-op for
        # the pilot book; the parameter is here for future books that need it.
        raw = _renumber(raw)

    resolver = checkpoints or HeuristicCheckpointResolver()
    plans = resolver.resolve(raw)
    # Drop sections that contain no narrative blocks (e.g. cover-only sections
    # that the heuristic picked up from a title page's h1/h2).  Their blocks
    # will get `section_id = None` (treated as front matter / cover).
    narrative_ids = {b.id for b in raw if b.is_narrative}
    kept_plans: list = []
    for plan in plans:
        end = _next_plan_start(plans, plan)
        span = [b.id for b in raw if plan.start_block_id <= b.id < end]
        if any(bid in narrative_ids for bid in span):
            kept_plans.append(plan)
        else:
            logger.info("Dropping section %d (no narrative blocks in span).", plan.id)
    plans = kept_plans
    logger.info("Checkpoint resolver kept %d non-empty sections.", len(plans))

    section_pairs = assign_section_ids(raw, plans)
    section_map = {bid: sid for bid, sid in section_pairs}
    book_blocks = _to_book_blocks(raw, section_map)

    # Build section list — only sections that actually have blocks
    used = {b.section_id for b in book_blocks if b.section_id is not None}
    sections = sorted(used)

    master = BookMaster(
        book_id=book_id,
        metadata=BookMetadata(
            title=title,
            author=author,
            publication_year=year,
            language=language,
        ),
        sections=[BookSection(id=sid) for sid in sections],
        blocks=book_blocks,
        chunks=[],
    )

    chunker = chunker or NarrativeChunker()
    master = chunker.chunk(master)
    master = recompute_offsets(master)
    logger.info("Produced %d chunks (target tokens %d).", len(master.chunks), chunker.params.target_tokens)

    master_path = write_book_master(master, str(pre_dir / "book.master.json"))
    reader_path = write_reader(master, str(reader_dir / "reader.json"))
    retrieval_path = write_retrieval(
        master,
        str(retrieval_dir / "retrieval.jsonl"),
        questions_per_chunk=questions_per_chunk,
    )
    logger.info("Wrote master → %s", master_path)
    logger.info("Wrote reader → %s", reader_path)
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
