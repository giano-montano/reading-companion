"""
Checkpoint resolvers — decide where pedagogical sections (and thus
checkpoints) fall in the book.

IMPORTANT (per Chang, 2026-07-05): sections are NOT book chapters.  They
are manual *pausas pedagógicas* marked by the teacher.  The default flow
produces a master with `sections: []` and every `block.section_id = None`.
The resolver in this file is OPT-IN.

Available strategies, swappable via CLI / constructor:

  * HeuristicCheckpointResolver — every <h1> or <h2> with non-empty text
    opens a new section.  EMITS A WARNING that this is only a guess based
    on the EPUB's own chapter structure, not a pedagogical decision.  Use
    it only to explore a book; the real pausas must be marked by hand.

  * JsonCheckpointResolver — read `data/<book_id>/checkpoints.json` (or
    any path you pass) with shape
        {"sections": [
            {"id": 1, "start_block_id": 4,  "note": "Pausa tras ..."},
            {"id": 2, "start_block_id": 78, "note": "Pausa tras ..."}
        ]}
    `id` and `note` are optional; `start_block_id` is required.  If `id`
    is missing, sections are numbered 1, 2, 3... in the order they appear.
    Anything before the first `start_block_id` keeps `section_id = None`
    (cover / front matter).

The resolver never splits blocks.  It only returns the *desired*
start_block_id per section; BookBuilder reconciles.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from companion.corpus.epub_loader import RawBlock

logger = logging.getLogger(__name__)


@dataclass
class SectionPlan:
    """A planned section.  `start_block_id` is the first block IN the section."""
    id: int
    start_block_id: int
    note: str = ""


class CheckpointResolver(ABC):
    @abstractmethod
    def resolve(self, blocks: list[RawBlock]) -> list[SectionPlan]:
        """Return section plans, in order, covering all narrative blocks."""


class HeuristicCheckpointResolver(CheckpointResolver):
    """
    A new section starts at every <h1> or <h2> with non-empty text.
    Headers are themselves part of the section (so the title of Cap. 1 has
    `section_id = 1`).

    This is NOT a pedagogical decision.  It mirrors the EPUB's own chapter
    structure.  Use only to explore; the real pausas must be marked by
    hand via `JsonCheckpointResolver`.
    """

    def resolve(self, blocks: list[RawBlock]) -> list[SectionPlan]:
        logger.warning(
            "HeuristicCheckpointResolver is enabled.  These sections are an "
            "inference from the EPUB's chapter structure, NOT pedagogical "
            "pausas.  Use --checkpoints=json with a hand-curated "
            "checkpoints.json for the real ones."
        )
        starts: list[int] = []
        for b in blocks:
            if b.content.startswith("<h1") or b.content.startswith("<h2"):
                starts.append(b.id)
        starts = sorted(set(starts))
        return [SectionPlan(id=i + 1, start_block_id=sid) for i, sid in enumerate(starts)]


class JsonCheckpointResolver(CheckpointResolver):
    """Apply a hand-curated checkpoint list from a JSON file."""

    def __init__(self, json_path: str) -> None:
        p = Path(json_path)
        if not p.exists():
            raise FileNotFoundError(f"checkpoints.json not found: {json_path}")
        data = json.loads(p.read_text(encoding="utf-8"))
        sections = data.get("sections") or []
        if not isinstance(sections, list) or not sections:
            raise ValueError("checkpoints.json: 'sections' must be a non-empty list")
        plans: list[SectionPlan] = []
        for i, entry in enumerate(sections, start=1):
            if not isinstance(entry, dict) or "start_block_id" not in entry:
                raise ValueError(
                    f"checkpoints.json: each entry needs 'start_block_id', got {entry!r}"
                )
            plans.append(
                SectionPlan(
                    id=int(entry.get("id", i)),
                    start_block_id=int(entry["start_block_id"]),
                    note=str(entry.get("note", "")),
                )
            )
        plans.sort(key=lambda p: p.start_block_id)
        # Re-number deterministically in reading order (1, 2, 3...).
        for i, plan in enumerate(plans, start=1):
            plan.id = i
        self._plans = plans

    def resolve(self, blocks: list[RawBlock]) -> list[SectionPlan]:
        return list(self._plans)


def assign_section_ids(
    blocks: list[RawBlock], plans: list[SectionPlan]
) -> list[tuple[int, int | None]]:
    """
    Map each block → (block_id, section_id).  Blocks before the first plan
    (or after the last plan, which shouldn't happen) get `section_id = None`.
    """
    boundaries = [(p.id, p.start_block_id) for p in plans]
    out: list[tuple[int, int | None]] = []
    for b in blocks:
        section_id: int | None = None
        for plan_id, start in boundaries:
            if b.id >= start:
                section_id = plan_id
        out.append((b.id, section_id))
    return out
