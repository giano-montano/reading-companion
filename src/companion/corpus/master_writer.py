"""
Master writer — serialize a `BookMaster` to `book.master.json`.

Format mirrors `data/master/master.md` exactly.  Numbers are written as ints
(not strings), booleans as booleans, and the `is_narrative` / `token_count`
fields are intentionally NOT written — they are derived metadata, not part
of the published contract.
"""
from __future__ import annotations

import json
from pathlib import Path

from companion.corpus.book_master import BookMaster


def write_book_master(master: BookMaster, out_path: str) -> Path:
    payload = {
        "book_id": master.book_id,
        "metadata": master.metadata.model_dump(exclude_none=True),
        "sections": [s.model_dump() for s in master.sections],
        "blocks": [
            {
                "id": b.id,
                "section_id": b.section_id,
                "content": b.content,
                "chunk_id": b.chunk_id,
            }
            for b in master.blocks
        ],  # text/is_narrative/token_count are derived, not published
        "chunks": [
            {
                "id": c.id,
                "section_ids": c.section_ids,
                "start_block_id": c.start_block_id,
                "end_block_id": c.end_block_id,
                "text": c.text,
                "char_start": c.char_start,
                "char_end": c.char_end,
            }
            for c in master.chunks
        ],
    }
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
