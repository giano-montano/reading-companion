"""
Reader writer — produce `reader.json` for the frontend.

Format mirrors `data/outputs/readers/reader.md`.  Sections get their
`start_block_id` / `end_block_id` computed from the master blocks.
"""
from __future__ import annotations

import json
from pathlib import Path

from companion.corpus.book_master import BookMaster


def write_reader(master: BookMaster, out_path: str) -> Path:
    by_section: dict[int, list[int]] = {}
    for b in master.blocks:
        if b.section_id is not None:
            by_section.setdefault(b.section_id, []).append(b.id)

    sections_payload = []
    for section in master.sections:
        block_ids = by_section.get(section.id, [])
        if not block_ids:
            continue
        sections_payload.append(
            {
                "id": section.id,
                "start_block_id": min(block_ids),
                "end_block_id": max(block_ids),
            }
        )

    blocks_payload = [
        {
            "id": b.id,
            "section_id": b.section_id,
            "content": b.content,
            "chunk_id": b.chunk_id,
        }
        for b in master.blocks
    ]

    payload = {
        "book_id": master.book_id,
        "metadata": master.metadata.model_dump(exclude_none=True),
        "sections": sections_payload,
        "blocks": blocks_payload,
    }
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
