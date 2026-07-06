"""
Sectioner — split blocks at pedagogical pause points and assign section_ids.

apply_pauses(master, spots) takes a BookMaster with no sections and a list
of pause spots.  Each spot is either:

  * a plain int block_id     → section starts at that block (no split).
  * a tuple (block_id, str)  → split the block's content AFTER the first
    occurrence of the given string; the section starts at the TAIL fragment.

After splitting and renumbering, every block gets its section_id assigned,
the chunker is re-run (chunks may now span two sections), and
char_start/char_end are recomputed.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

from companion.chunkers.narrative import NarrativeChunker
from companion.corpus.book_master import BookBlock, BookMaster, BookSection
from companion.corpus.canonical_text import recompute_offsets, validate_offsets

logger = logging.getLogger(__name__)


@dataclass
class SectionSpot:
    block_id: int
    split_after: str | None = None   # text to split AFTER (kept in the first fragment)


def _split_html_at_text(html: str, split_pos: int) -> tuple[str, str] | None:
    """Split HTML at the given text position, keeping tags balanced."""
    import re as re_m
    head: list[str] = []
    tail: list[str] = []
    text_pos = 0
    i = 0
    in_tag = False
    open_stack: list[str] = []
    buf: list[str] = []
    done = False

    while i < len(html):
        ch = html[i]
        if ch == "<":
            if buf:
                if done:
                    tail.append("".join(buf))
                else:
                    head.append("".join(buf))
                buf = []
            in_tag = True
            tag_start = i
            while i < len(html) and html[i] != ">":
                i += 1
            if i < len(html):
                i += 1
            tag = html[tag_start:i]
            if done:
                tail.append(tag)
            else:
                head.append(tag)
            stripped = tag.strip()
            if stripped.startswith("</"):
                if open_stack:
                    open_stack.pop()
            elif not stripped.endswith("/>") and not stripped.lower().startswith("<br") \
                    and not stripped.lower().startswith("<hr"):
                m = re_m.match(r"<([a-zA-Z0-9]+)", stripped)
                if m:
                    open_stack.append(m.group(1).lower())
            in_tag = False
            continue

        if not in_tag:
            if not done and text_pos == split_pos:
                buf.append(ch)
                head.append("".join(buf))
                buf = []
                for tag in reversed(open_stack):
                    head.append(f"</{tag}>")
                tail.append("")
                for tag in open_stack:
                    tail.append(f"<{tag}>")
                done = True
            else:
                buf.append(ch)
            text_pos += 1
        i += 1

    if buf:
        if done:
            tail.append("".join(buf))
        else:
            head.append("".join(buf))

    h = "".join(head).strip()
    t = "".join(tail).strip()
    if not h or not t:
        return None
    return h, t


def apply_pauses(
    master: BookMaster,
    spots: list[SectionSpot],
    token_count: Callable[[str], int] | None = None,
) -> BookMaster:
    """
    Apply pedagogical pauses to a master that currently has no sections.

    For each spot:
      - If split_after is None: the section starts at the given block_id.
      - If split_after is set: split the block's content and text at that
        point; the new section starts at the tail fragment.

    After applying, blocks are renumbered (1, 2, 3, ...), section_ids are
    assigned sequentially, the chunker is re-run (so chunks may span two
    sections), and char_start/char_end are recomputed.
    """
    if not spots:
        return master

    spots = sorted(spots, key=lambda s: s.block_id)

    # 1) Split blocks at the marked positions.
    new_section_starts: list[int] = []
    new_blocks: list[BookBlock] = []
    next_id = 1
    for b in master.blocks:
        spot = next((s for s in spots if s.block_id == b.id), None)
        if spot is not None and spot.split_after:
            # Split this block.
            plain_text = b.text
            html = b.content
            idx = plain_text.find(spot.split_after)
            if idx == -1:
                logger.warning(
                    "Could not find %r in block %d text; keeping block intact.",
                    spot.split_after, b.id,
                )
                new_blocks.append(_copy(b, next_id, section_id=None))
                new_section_starts.append(next_id)
                next_id += 1
                continue
            split_pos = idx + len(spot.split_after)
            before_text = plain_text[:split_pos].rstrip()
            after_text = plain_text[split_pos:].lstrip()
            if not before_text or not after_text:
                logger.warning(
                    "Split at %r in block %d would produce empty fragment; keeping block intact.",
                    spot.split_after, b.id,
                )
                new_blocks.append(_copy(b, next_id, section_id=None))
                new_section_starts.append(next_id)
                next_id += 1
                continue
            html_parts = _split_html_at_text(html, split_pos)
            if html_parts is None:
                logger.warning(
                    "Could not split HTML for block %d; keeping block intact.", b.id,
                )
                new_blocks.append(_copy(b, next_id, section_id=None))
                new_section_starts.append(next_id)
                next_id += 1
                continue
            before_html, after_html = html_parts
            new_blocks.append(_copy(
                b, next_id, section_id=None,
                text=before_text, content=before_html,
            ))
            next_id += 1
            new_section_starts.append(next_id)
            new_blocks.append(_copy(
                b, next_id, section_id=None,
                text=after_text, content=after_html,
            ))
            next_id += 1
        else:
            new_blocks.append(_copy(b, next_id, section_id=None))
            if spot is not None:
                new_section_starts.append(next_id)
            next_id += 1

    # 2) Renumber all blocks.
    for i, b in enumerate(new_blocks, start=1):
        b.id = i
    # Update section_starts to match new numbering.
    old_to_new: dict[int, int] = {}
    for old_b, new_b in zip(master.blocks, new_blocks):
        old_to_new.setdefault(old_b.id, new_b.id)
    new_starts: list[int] = []
    seen: set[int] = set()
    for start in new_section_starts:
        new_id = old_to_new.get(start, start)
        if new_id not in seen:
            new_starts.append(new_id)
            seen.add(new_id)

    # 3) Assign section_id.
    # Blocks before the first section start get section_id = 1
    # (they are the first narrative segment after the cover, which
    #  has already been filtered as section_id = None upstream).
    first_start = new_starts[0] if new_starts else 10**9
    for b in new_blocks:
        if b.id < first_start:
            b.section_id = 1 if new_starts else None
            continue
        section_id: int | None = None
        for idx, start in enumerate(new_starts, start=1):
            if b.id >= start:
                section_id = idx
        b.section_id = section_id

    used_sections = sorted({b.section_id for b in new_blocks if b.section_id is not None})
    master.blocks = new_blocks
    master.sections = [BookSection(id=s) for s in used_sections]

    # 4) Re-run chunker.
    chunker = NarrativeChunker()
    master = chunker.chunk(master)
    master = recompute_offsets(master)
    validate_offsets(master)

    logger.info(
        "Applied %d pauses: %d sections, %d blocks total, %d chunks.",
        len(spots), len(master.sections), len(master.blocks), len(master.chunks),
    )
    return master


def _copy(b: BookBlock, new_id: int, **overrides) -> BookBlock:
    data = {
        "id": new_id,
        "section_id": b.section_id,
        "content": b.content,
        "text": b.text,
        "chunk_id": None,
        "is_narrative": b.is_narrative,
        "token_count": 0,
    }
    data.update(overrides)
    return BookBlock(**data)
