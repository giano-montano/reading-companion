"""Rebuild reader from master.json: split narrative blocks at exact chunk boundaries.

Uses the last characters of each chunk's text to find the exact split position
in the block text. Preserves all original block types and non-narrative blocks.
BANDERAs are kept unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MASTER_DIR = ROOT / "data" / "master"
READER_DIR = ROOT / "data" / "outputs" / "readers"
RETRIEVAL_DIR = ROOT / "data" / "outputs" / "retrieval"

MATCH_CHARS = 60  # how many trailing chars of chunk text to match for split point


def _find_split(text: str, needle: str) -> int:
    """Find the end position of `needle` in `text`. Returns position after needle."""
    idx = text.find(needle)
    if idx >= 0:
        return idx + len(needle)
    # Try shorter match
    for trim in range(1, len(needle), 5):
        shorter = needle[trim:]
        idx = text.find(shorter)
        if idx >= 0:
            return idx + len(shorter)
    return -1


def rebuild_one(book_id: str, master_path: Path, retrieval_path: Path) -> dict:
    master = json.loads(master_path.read_text(encoding="utf-8"))
    old_blocks = master["blocks"]

    with open(retrieval_path, "r", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]

    if not chunks:
        return master

    # Precompute: for each chunk, get a "search tail" (last MATCH_CHARS of its text)
    # and the boundary position (next chunk's char_start)
    chunk_info = []
    for i, chunk in enumerate(chunks):
        tail = chunk["text"][-MATCH_CHARS:] if len(chunk["text"]) >= MATCH_CHARS else chunk["text"]
        if i < len(chunks) - 1:
            boundary = chunks[i + 1]["metadata"]["char_start"]
        else:
            boundary = chunk["metadata"]["char_end"]
        chunk_info.append({
            "chunk_id": chunk["chunk_id"],
            "tail": tail,
            "boundary": boundary,
            "char_start": chunk["metadata"]["char_start"],
            "char_end": chunk["metadata"]["char_end"],
        })

    new_blocks: list[dict] = []
    canon_pos = 0  # track position in canonical text

    for block in old_blocks:
        btype = block["type"]

        if btype == "BANDERA":
            new_blocks.append(dict(block))
            continue

        if not block["is_narrative"]:
            nb = dict(block)
            nb["chunk_id"] = None
            new_blocks.append(nb)
            canon_pos += len(block["text"]) + 2
            continue

        # Narrative block
        b_text = block["text"]
        b_start = block["char_start"]
        b_end = block["char_end"]

        if b_end <= b_start:
            nb = dict(block)
            nb["chunk_id"] = None
            new_blocks.append(nb)
            continue

        # Find chunks whose boundary falls inside this block
        boundaries = []  # list of (canonical_pos, chunk_id_before)
        for ci in chunk_info:
            if b_start < ci["boundary"] < b_end:
                boundaries.append(ci["boundary"])

        if not boundaries:
            # Block fits in one chunk: assign chunk_id
            mid = (b_start + b_end) // 2
            cid = None
            for ci in chunk_info:
                if ci["char_start"] <= mid < ci["char_end"]:
                    cid = ci["chunk_id"]
                    break
            nb = dict(block)
            nb["chunk_id"] = cid
            new_blocks.append(nb)
            canon_pos += len(block["text"]) + 2
            continue

        # Block spans multiple chunks: split at each boundary
        # Use chunk tails to find exact split positions in text
        unique_boundaries = sorted(set(boundaries))
        split_positions = []  # positions in block text (relative to block start)

        for boundary in unique_boundaries:
            # Find the chunk whose next boundary is this one
            for ci in chunk_info:
                if ci["boundary"] == boundary:
                    # ci is the chunk BEFORE the boundary
                    # Try to find its tail in the block text
                    pos = _find_split(b_text, ci["tail"])
                    if pos > 0:
                        split_positions.append(pos)
                    break
            else:
                # Fallback: use canonical position
                rel = boundary - b_start
                if 0 < rel < len(b_text):
                    split_positions.append(rel)

        # Ensure clean splits
        split_positions = sorted(set([0] + [p for p in split_positions if 0 < p < len(b_text)] + [len(b_text)]))

        for i in range(len(split_positions) - 1):
            seg_start_rel = split_positions[i]
            seg_end_rel = split_positions[i + 1]
            if seg_end_rel <= seg_start_rel:
                continue
            text = b_text[seg_start_rel:seg_end_rel]
            if not text.strip():
                continue

            seg_start = b_start + seg_start_rel
            seg_end = b_start + seg_end_rel
            mid = (seg_start + seg_end) // 2

            # Find chunk for this segment
            cid = None
            for ci in chunk_info:
                if ci["char_start"] <= mid < ci["boundary"]:
                    cid = ci["chunk_id"]
                    break

            new_blocks.append({
                "id_block": "",
                "type": btype,
                "text": text,
                "chunk_id": cid,
                "char_start": seg_start,
                "char_end": seg_end,
                "is_narrative": True,
            })

        canon_pos += len(block["text"]) + 2

    # Reindex
    for idx, b in enumerate(new_blocks):
        b["id_block"] = f"{master['book_id']}::block::{idx + 1}"

    return {
        "book_id": master["book_id"],
        "metadata": master["metadata"],
        "blocks": new_blocks,
    }


def main():
    for mp in sorted(MASTER_DIR.glob("*.master.json")):
        book_id = mp.stem.replace(".master", "")
        ret_path = RETRIEVAL_DIR / f"{book_id}.retrieval.jsonl"
        if not ret_path.exists():
            print(f"  SKIP {mp.name}: no retrieval")
            continue

        reader = rebuild_one(book_id, mp, ret_path)
        reader_path = READER_DIR / f"{book_id}.reader.json"
        reader_path.parent.mkdir(parents=True, exist_ok=True)
        with open(reader_path, "w", encoding="utf-8") as f:
            json.dump(reader, f, ensure_ascii=False, indent=2)
            f.write("\n")

        blocks = reader["blocks"]
        narr = [b for b in blocks if b["is_narrative"]]
        banderas = [b for b in blocks if b["type"] == "BANDERA"]
        non_narr = [b for b in blocks if not b["is_narrative"] and b["type"] != "BANDERA"]
        chunks = set(b.get("chunk_id") for b in narr if b.get("chunk_id"))
        bpc = len(narr) / len(chunks) if chunks else 0
        types = sorted(set(b["type"] for b in blocks))
        print(f"  {reader_path.name}: {len(blocks)} blocks "
              f"({len(narr)} narr -> {len(chunks)} chunks, {bpc:.1f}b/c, "
              f"{len(non_narr)} paratext, {len(banderas)} banderas) types={types}")


if __name__ == "__main__":
    main()
