"""
Checkpoint resolvers — decide where pedagogical sections (and thus
checkpoints) fall in the book.

Two strategies, swappable via CLI / constructor:

  * HeuristicCheckpointResolver (default): any <h1> or <h2> with non-empty
    text opens a new section.  Blocks before the first heading are
    `section_id = None` (cover, title page, index).

  * JsonCheckpointResolver: read `data/books/<book_id>/preprocessing/
    checkpoints.json` with shape
        {"sections": [{"start_block_id": 4}, {"start_block_id": 80}, ...]}
    and apply exactly that.  Anything before the first listed start_block_id
    is section_id = None.

The resolver never splits blocks — that's `block_splitting.py`'s job.  It only
returns the *desired* start_block_id per section; BookBuilder reconciles.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from companion.corpus.epub_loader import RawBlock


@dataclass
class SectionPlan:
    """A planned section.  `start_block_id` is the first block IN the section."""
    id: int
    start_block_id: int


class CheckpointResolver(ABC):
    @abstractmethod
    def resolve(self, blocks: list[RawBlock]) -> list[SectionPlan]:
        """Return section plans, in order, covering all narrative blocks."""


class HeuristicCheckpointResolver(CheckpointResolver):
    """
    A new section starts at every <h1> or <h2> with non-empty text.
    Headers are themselves part of the section (so the title of Cap. 1 has
    `section_id = 1`).
    """

    def resolve(self, blocks: list[RawBlock]) -> list[SectionPlan]:
        starts: list[int] = []
        for b in blocks:
            if b.content.startswith("<h1") or b.content.startswith("<h2"):
                starts.append(b.id)

        # Dedupe (rare) and ensure monotonically increasing
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
        starts: list[int] = []
        for entry in sections:
            if not isinstance(entry, dict) or "start_block_id" not in entry:
                raise ValueError(
                    f"checkpoints.json: each entry needs 'start_block_id', got {entry!r}"
                )
            starts.append(int(entry["start_block_id"]))
        starts = sorted(set(starts))
        self._plans = [SectionPlan(id=i + 1, start_block_id=sid) for i, sid in enumerate(starts)]

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
