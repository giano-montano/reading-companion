"""Rebuild reader from master.json: split narrative blocks at chunk boundaries.

Finds each retrieval chunk's position in the narrative-only canonical text
via str.find — exact match confirmed. All narrative block positions use
the narrative-only coordinate system for consistency.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MASTER_DIR = ROOT / "data" / "master"
READER_DIR = ROOT / "data" / "outputs" / "readers"
RETRIEVAL_DIR = ROOT / "data" / "outputs" / "retrieval"


def rebuild_one(book_id: str, master_path: Path, retrieval_path: Path) -> dict:
    master = json.loads(master_path.read_text(encoding="utf-8"))
    old_blocks = master["blocks"]

    with open(retrieval_path, "r", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]

    if not chunks:
        return master

    narr_indices = []
    narr_texts = []
    for i, b in enumerate(old_blocks):
        if b["is_narrative"] and b["type"] != "BANDERA":
            narr_indices.append(i)
            narr_texts.append(b["text"])

    if not narr_texts:
        return master

    narr_canon = "\n\n".join(narr_texts)

    narr_ranges = []
    pos = 0
    for text in narr_texts:
        start = pos
        end = pos + len(text)
        narr_ranges.append((start, end))
        pos = end + 2

    chunk_info = []
    for chunk in chunks:
        ctext = chunk["text"]
        fpos = narr_canon.find(ctext)
        if fpos >= 0:
            chunk_info.append({
                "chunk_id": chunk["chunk_id"],
                "real_start": fpos,
                "real_end": fpos + len(ctext),
            })
        else:
            m = chunk["metadata"]
            chunk_info.append({
                "chunk_id": chunk["chunk_id"],
                "real_start": m["char_start"],
                "real_end": m["char_end"],
            })

    chunk_boundaries = sorted(set(ci["real_end"] for ci in chunk_info))

    # new_narr_by_old_idx maps old narrative block index -> list of new block dicts
    new_narr_by_old_idx: dict[int, list[dict]] = {}

    for narr_i, (b_start, b_end) in enumerate(narr_ranges):
        old_idx = narr_indices[narr_i]
        block = old_blocks[old_idx]
        b_text = block["text"]

        inner = [cb for cb in chunk_boundaries if b_start < cb < b_end]
        segments: list[dict] = []

        if not inner:
            mid = (b_start + b_end) // 2
            cid = _find_chunk(chunk_info, mid)
            nb = dict(block)
            nb["chunk_id"] = cid
            nb["char_start"] = b_start
            nb["char_end"] = b_end
            segments.append(nb)
        else:
            split_points = [0]
            for cb in sorted(set(inner)):
                rel = cb - b_start
                if 0 < rel < len(b_text):
                    split_points.append(rel)
            split_points.append(len(b_text))
            split_points = sorted(set(split_points))

            for j in range(len(split_points) - 1):
                sr = split_points[j]
                er = split_points[j + 1]
                if er <= sr:
                    continue
                text = b_text[sr:er]
                if not text.strip():
                    continue

                seg_start = b_start + sr
                seg_end = b_start + er
                mid = (seg_start + seg_end) // 2
                cid = _find_chunk(chunk_info, mid)

                segments.append({
                    "id_block": "",
                    "type": block["type"],
                    "text": text,
                    "chunk_id": cid,
                    "char_start": seg_start,
                    "char_end": seg_end,
                    "is_narrative": True,
                })

        new_narr_by_old_idx[old_idx] = segments

    non_narr_map = {i: b for i, b in enumerate(old_blocks) if not b["is_narrative"] and b["type"] != "BANDERA"}
    bandera_map = {i: b for i, b in enumerate(old_blocks) if b["type"] == "BANDERA"}

    final: list[dict] = []
    for i in range(len(old_blocks)):
        if i in bandera_map:
            final.append(dict(bandera_map[i]))
        elif i in non_narr_map:
            final.append(dict(non_narr_map[i]))
        elif i in new_narr_by_old_idx:
            for seg in new_narr_by_old_idx[i]:
                final.append(seg)

    # Merge adjacent narrative blocks with same type.
    # First pass: same chunk_id.
    merged = _merge_adjacent(final, require_same_chunk=True)
    # Second pass: same type regardless of chunk_id, for tiny boundary fragments.
    merged = _merge_adjacent(merged, require_same_chunk=False, max_result_len=200)

    for idx, b in enumerate(merged):
        b["id_block"] = f"{master['book_id']}::block::{idx + 1}"

    return {
        "book_id": master["book_id"],
        "metadata": master["metadata"],
        "blocks": merged,
    }


def _merge_adjacent(
    blocks: list[dict],
    require_same_chunk: bool,
    max_result_len: int = 0,
) -> list[dict]:
    merged: list[dict] = []
    for b in blocks:
        if not b["is_narrative"]:
            merged.append(b)
            continue
        if merged and merged[-1]["is_narrative"] and merged[-1]["type"] == b["type"]:
            same_chunk = merged[-1].get("chunk_id") == b.get("chunk_id")
            can_merge = same_chunk if require_same_chunk else True
            if can_merge:
                new_len = len(merged[-1]["text"]) + len(b["text"])
                is_tiny = len(b["text"]) < 5
                if max_result_len == 0 or new_len <= max_result_len or is_tiny:
                    prev = merged[-1]
                    prev["text"] = prev["text"] + b["text"]
                    prev["char_end"] = b["char_end"]
                    continue
        merged.append(b)
    return merged


def _find_chunk(chunk_info: list[dict], canon_pos: int) -> str | None:
    for ci in chunk_info:
        if ci["real_start"] <= canon_pos < ci["real_end"]:
            return ci["chunk_id"]
    if canon_pos >= chunk_info[-1]["real_end"]:
        return chunk_info[-1]["chunk_id"]
    if canon_pos < chunk_info[0]["real_start"]:
        return chunk_info[0]["chunk_id"]
    return None


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
        tiny = sum(1 for b in narr if 0 < len(b["text"]) < 5)
        periods = sum(1 for b in narr if b["text"] == ".")
        null_c = sum(1 for b in narr if b.get("chunk_id") is None)
        bpc = len(narr) / len(chunks) if chunks else 0
        print(f"  {reader_path.name}: {len(blocks)} blocks "
              f"({len(narr)} narr -> {len(chunks)} chunks, {bpc:.1f}b/c, "
              f"{tiny} tiny, {periods} periods, {null_c} null, "
              f"{len(non_narr)} paratext, {len(banderas)} banderas)")


if __name__ == "__main__":
    main()
