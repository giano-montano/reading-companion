"""
generate_chunks.py — Chunk narrative blocks from master.json files using a real tokenizer.

Reads all data/master/*.master.json, fills the "chunks" array and updates
"chunk_id" on narrative blocks. Idempotent. No embeddings, no vector DB.
"""

from __future__ import annotations

import json
import os
import statistics
from pathlib import Path

from dotenv import load_dotenv
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent.parent
MASTER_DIR = ROOT / "data" / "master"

# ── chunking parameters ──────────────────────────────────────────────
MIN_SEARCH_TOKENS = 350
SOFT_MAX_TOKENS = 470
HARD_MAX_TOKENS = 500
OVERLAP_TARGET_TOKENS = 100
OVERLAP_MIN_TOKENS = 60
MIN_CHUNK_TOKENS = 200

# ── boundary characters for clean sentence/paragraph cuts ─────────────
PARAGRAPH_BOUNDARY = "\n\n"
SENTENCE_ENDINGS = {".", "!", "?", ".\"", "!\"", "?\"", ")", "]", "»"}
DIALOGUE_END = {"—", "–", "-"}


def _load_tokenizer() -> AutoTokenizer:
    load_dotenv(ROOT / ".env")
    model_name = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
    print(f"  Tokenizer: {model_name}")
    return AutoTokenizer.from_pretrained(model_name)


def _build_canonical_and_offsets(
    narr_blocks: list[dict],
) -> tuple[str, list[tuple[int, int]]]:
    """Build canonical text from narrative blocks and return (text, offsets).

    offsets[i] = (char_start, char_end) of narr_blocks[i] in canonical text.
    """
    texts = [b["text"] for b in narr_blocks]
    canonical = "\n\n".join(texts)
    offsets = []
    pos = 0
    for i, t in enumerate(texts):
        start = pos
        end = pos + len(t)
        offsets.append((start, end))
        if i < len(texts) - 1:
            pos = end + 2  # "\n\n"
    return canonical, offsets


def _find_clean_boundary(
    text: str,
    target_pos: int,
    search_range: int = 150,
) -> int:
    """Find a clean boundary position near target_pos in text.
    Prefers paragraph breaks, then sentence endings, then spaces.
    Returns a position >= target_pos (forward search) or < target_pos (backward).
    """
    # Search backward from target_pos for a clean break
    search_start = max(0, target_pos - search_range)
    search_end = min(len(text), target_pos + search_range)

    # Prefer paragraph break
    para_idx = text.rfind("\n\n", search_start, target_pos + 50)
    if para_idx != -1 and target_pos - para_idx < search_range:
        return para_idx + 2  # after the double newline

    # Prefer sentence ending
    for i in range(target_pos, search_start, -1):
        if i < len(text) and text[i] in SENTENCE_ENDINGS:
            # Check if followed by space/newline or end of text
            if i + 1 >= len(text) or text[i + 1] in (" ", "\n", "\r"):
                return i + 1

    # Fall back to space
    space_idx = text.rfind(" ", search_start, target_pos + 30)
    if space_idx != -1:
        return space_idx + 1

    return target_pos


def _find_forward_boundary(text: str, target_pos: int, search_range: int = 80) -> int:
    """Find a clean start boundary forward from target_pos."""
    search_end = min(len(text), target_pos + search_range)

    # Prefer paragraph start
    para_idx = text.find("\n\n", target_pos, search_end)
    if para_idx != -1:
        return para_idx + 2

    # Sentence start: capital letter after sentence ending
    for i in range(target_pos, search_end):
        if i > 0 and text[i - 1] in SENTENCE_ENDINGS and text[i] in (" ", "\n"):
            # Find next non-space char
            j = i + 1
            while j < len(text) and text[j] in (" ", "\n", "\r", "\t"):
                j += 1
            if j < len(text) and text[j].isupper():
                return j

    # Fall back to space
    space_idx = text.find(" ", target_pos + 20, search_end)
    if space_idx != -1:
        return space_idx + 1

    return target_pos


def _clean_boundary_backward(text: str, target_pos: int) -> int:
    """Find clean boundary at or before target_pos (for overlap start)."""
    search_start = max(0, target_pos - 200)

    # Prefer paragraph start (after \n\n)
    para_idx = text.rfind("\n\n", search_start, target_pos + 1)
    if para_idx != -1:
        return para_idx + 2

    # Sentence start
    for i in range(target_pos, search_start, -1):
        if i > 0 and text[i - 1] in SENTENCE_ENDINGS and i < len(text) and text[i] in (" ", "\n", "\r"):
            j = i + 1
            while j < len(text) and text[j] in (" ", "\n", "\r", "\t"):
                j += 1
            if j < len(text) and (text[j].isupper() or text[j] in ("—", "«", "(")):
                return j
        elif i > 0 and text[i - 1] == "\n" and i < len(text):
            return i

    # Fall back to space
    space_idx = text.rfind(" ", search_start, target_pos)
    if space_idx != -1:
        return space_idx + 1

    return target_pos


def chunk_book(
    blocks: list[dict],
    tokenizer: AutoTokenizer,
    book_id: str,
) -> tuple[list[dict], list[dict], dict]:
    """Chunk narrative blocks. Returns (updated_blocks, chunks, stats)."""
    # Separate narrative blocks (non-bandera, is_narrative=true)
    narr_blocks = [b for b in blocks if b["is_narrative"] and b.get("type") != "BANDERA"]
    if not narr_blocks:
        return blocks, [], {}

    canonical, offsets = _build_canonical_and_offsets(narr_blocks)
    tokens = tokenizer.encode(canonical, add_special_tokens=False)
    total_tokens = len(tokens)

    # Map token positions to character positions for boundary finding
    # Build a token->char mapping using offset_mapping
    encoded = tokenizer(canonical, return_offsets_mapping=True, add_special_tokens=False)
    token_char_starts = [off[0] for off in encoded["offset_mapping"]]  # char start of each token
    token_char_ends = [off[1] for off in encoded["offset_mapping"]]    # char end of each token

    # ── Main chunking loop ───────────────────────────────────────────
    chunks_raw: list[dict] = []  # {char_start, char_end, text}
    pos = 0  # current token position
    hard_cuts = 0

    while pos < total_tokens:
        # Start of chunk
        chunk_start_char = token_char_starts[pos]

        # Accumulate tokens until we reach at least MIN_SEARCH_TOKENS
        search_end = min(pos + MIN_SEARCH_TOKENS, total_tokens)

        # Try to close chunk naturally
        # Walk forward looking for a good block boundary
        best_end = pos + MIN_SEARCH_TOKENS
        found_boundary = False

        for end_candidate in range(pos + MIN_SEARCH_TOKENS, min(pos + HARD_MAX_TOKENS + 1, total_tokens)):
            if end_candidate >= total_tokens:
                best_end = total_tokens
                found_boundary = True
                break

            # Check if this is a block boundary
            cand_char = token_char_ends[end_candidate - 1] if end_candidate > 0 else 0

            # Is cand_char at or near a block boundary?
            is_block_boundary = False
            for _, block_end_char in offsets:
                if abs(cand_char - block_end_char) <= 3:
                    is_block_boundary = True
                    break

            # Check for paragraph boundary (double newline)
            if is_block_boundary:
                # Found a block boundary - good place to close
                if end_candidate >= pos + MIN_SEARCH_TOKENS:
                    best_end = end_candidate
                    found_boundary = True
                    break
            elif end_candidate >= pos + SOFT_MAX_TOKENS:
                # Past SOFT_MAX - look for sentence boundary
                chunk_text_so_far = canonical[
                    token_char_starts[pos] : token_char_ends[end_candidate - 1]
                ]
                # Try to find a clean sentence boundary backward
                boundary = _find_clean_boundary(
                    canonical,
                    token_char_ends[end_candidate - 1],
                    search_range=100,
                )
                boundary_token = _char_to_token(boundary, token_char_starts, token_char_ends, pos)
                if boundary_token is not None and boundary_token > pos + MIN_SEARCH_TOKENS:
                    best_end = boundary_token
                    found_boundary = True
                    break

        if not found_boundary:
            # Force close at HARD_MAX or end
            best_end = min(pos + HARD_MAX_TOKENS, total_tokens)
            if best_end > pos + SOFT_MAX_TOKENS:
                hard_cuts += 1
            # Try to find a clean boundary anyway
            boundary = _find_clean_boundary(
                canonical,
                token_char_ends[best_end - 1] if best_end > 0 else 0,
                search_range=80,
            )
            boundary_token = _char_to_token(boundary, token_char_starts, token_char_ends, pos)
            if boundary_token is not None and boundary_token > pos + MIN_SEARCH_TOKENS:
                best_end = boundary_token

        # Build chunk
        chunk_end_char = token_char_ends[best_end - 1] if best_end > 0 else token_char_starts[best_end] if best_end < total_tokens else len(canonical)
        chunk_text = canonical[chunk_start_char:chunk_end_char]

        chunks_raw.append({
            "char_start": chunk_start_char,
            "char_end": chunk_end_char,
            "text": chunk_text,
        })

        # ── Overlap: next chunk starts earlier ────────────────────────
        if best_end >= total_tokens:
            break

        # Target overlap start in char space
        overlap_target_char = chunk_end_char
        # Go back OVERLAP_TARGET_TOKENS tokens
        overlap_token_pos = max(pos, best_end - OVERLAP_TARGET_TOKENS)
        overlap_char_pos = token_char_starts[overlap_token_pos]

        # Find clean boundary for overlap start
        clean_start = _clean_boundary_backward(canonical, overlap_char_pos)
        clean_start_token = _char_to_token(clean_start, token_char_starts, token_char_ends, 0)

        if clean_start_token is None:
            clean_start_token = overlap_token_pos

        # Ensure minimum overlap
        if best_end - clean_start_token < OVERLAP_MIN_TOKENS:
            # Go back further
            clean_start_token = max(pos, best_end - OVERLAP_TARGET_TOKENS * 2)
            clean_char = token_char_starts[clean_start_token]
            cleaner = _clean_boundary_backward(canonical, clean_char)
            cleaner_token = _char_to_token(cleaner, token_char_starts, token_char_ends, 0)
            if cleaner_token is not None:
                clean_start_token = cleaner_token

        pos = clean_start_token

    # ── Merge small chunks ────────────────────────────────────────────
    merged = 0
    i = 0
    while i < len(chunks_raw):
        chunk = chunks_raw[i]
        chunk_tokens = _count_tokens(chunk["text"], tokenizer)
        if chunk_tokens < MIN_CHUNK_TOKENS and i > 0:
            prev = chunks_raw[i - 1]
            prev_tokens = _count_tokens(prev["text"], tokenizer)
            combined_text = prev["text"] + "\n\n" + chunk["text"]
            combined_tokens = _count_tokens(combined_text, tokenizer)
            if combined_tokens <= HARD_MAX_TOKENS + 50:  # small tolerance
                prev["text"] = combined_text
                prev["char_end"] = chunk["char_end"]
                chunks_raw.pop(i)
                merged += 1
                continue
        i += 1

    # ── Assign chunk_ids and build final chunks ───────────────────────
    final_chunks = []
    for idx, chunk in enumerate(chunks_raw):
        chunk_id = f"{book_id}::chunk::{idx + 1}"
        final_chunks.append({
            "id_chunk": chunk_id,
            "text": chunk["text"],
            "char_start": chunk["char_start"],
            "char_end": chunk["char_end"],
        })

    # ── Assign chunk_id to blocks ─────────────────────────────────────
    # Each narrative block gets the id of the FIRST chunk that contains it
    for block in narr_blocks:
        block_char_start = block["char_start"]
        block_char_end = block["char_end"]
        assigned = False
        for chunk in final_chunks:
            # Block is in chunk if its range is within chunk's range
            if block_char_start >= chunk["char_start"] and block_char_end <= chunk["char_end"]:
                block["chunk_id"] = chunk["id_chunk"]
                assigned = True
                break
        # If block spans across chunks (split block), assign to first chunk containing it
        if not assigned:
            for chunk in final_chunks:
                if block_char_start >= chunk["char_start"] and block_char_start < chunk["char_end"]:
                    block["chunk_id"] = chunk["id_chunk"]
                    assigned = True
                    break
        # If still not assigned (edge case), assign to first chunk
        if not assigned and final_chunks:
            block["chunk_id"] = final_chunks[0]["id_chunk"]

    # ── Update original blocks array ──────────────────────────────────
    # Only modify chunk_id for narrative blocks; leave others as null
    for block in blocks:
        if block.get("type") == "BANDERA":
            block["chunk_id"] = None
        elif not block["is_narrative"]:
            block["chunk_id"] = None
        # narrative blocks already have chunk_id assigned above

    # ── Stats ─────────────────────────────────────────────────────────
    chunk_tokens_list = [_count_tokens(c["text"], tokenizer) for c in final_chunks]
    chunk_chars_list = [len(c["text"]) for c in final_chunks]

    stats = {
        "num_chunks": len(final_chunks),
        "narr_blocks_used": len(narr_blocks),
        "blocks_ignored": len(blocks) - len(narr_blocks),
        "avg_tokens": round(statistics.mean(chunk_tokens_list), 1) if chunk_tokens_list else 0,
        "min_tokens": min(chunk_tokens_list) if chunk_tokens_list else 0,
        "max_tokens": max(chunk_tokens_list) if chunk_tokens_list else 0,
        "median_tokens": round(statistics.median(chunk_tokens_list), 1) if chunk_tokens_list else 0,
        "avg_chars": round(statistics.mean(chunk_chars_list), 1) if chunk_chars_list else 0,
        "min_chars": min(chunk_chars_list) if chunk_chars_list else 0,
        "max_chars": max(chunk_chars_list) if chunk_chars_list else 0,
        "hard_cuts": hard_cuts,
        "merged_chunks": merged,
    }

    return blocks, final_chunks, stats


def _char_to_token(
    char_pos: int,
    token_starts: list[int],
    token_ends: list[int],
    min_token: int = 0,
) -> int | None:
    """Find the token index that starts at or contains char_pos."""
    for i in range(min_token, len(token_starts)):
        if token_starts[i] <= char_pos < token_ends[i]:
            return i
        if token_starts[i] >= char_pos:
            return i
    return None


def _count_tokens(text: str, tokenizer: AutoTokenizer) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def process_file(fp: Path, tokenizer: AutoTokenizer) -> dict:
    """Process one master.json file. Returns stats dict."""
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)

    book_id = data["book_id"]

    # Idempotent: reset chunks and chunk_ids
    data["chunks"] = []
    for b in data["blocks"]:
        b["chunk_id"] = None

    blocks, chunks, stats = chunk_book(data["blocks"], tokenizer, book_id)

    data["blocks"] = blocks
    data["chunks"] = chunks

    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    stats["file"] = fp.name
    stats["book_id"] = book_id
    return stats


# ── Validation ────────────────────────────────────────────────────────
def validate(data: dict) -> list[str]:
    errors = []
    blocks = data["blocks"]
    chunks = data["chunks"]
    book_id = data["book_id"]

    # 1. No BANDERA should have chunk_id
    for b in blocks:
        if b.get("type") == "BANDERA" and b.get("chunk_id") is not None:
            errors.append(f"BANDERA {b['id_block']} has chunk_id={b['chunk_id']}")

    # 2. No non-narrative should have chunk_id
    for b in blocks:
        if not b["is_narrative"] and b.get("type") != "BANDERA" and b.get("chunk_id") is not None:
            errors.append(f"Non-narrative {b['id_block']} has chunk_id={b['chunk_id']}")

    # 3. All narrative used blocks must have chunk_id
    for b in blocks:
        if b["is_narrative"] and b.get("type") != "BANDERA":
            if b.get("chunk_id") is None:
                errors.append(f"Narrative block {b['id_block']} has no chunk_id")

    # 4. chunks not empty if narr blocks exist
    narr_count = sum(1 for b in blocks if b["is_narrative"] and b.get("type") != "BANDERA")
    if narr_count > 0 and len(chunks) == 0:
        errors.append("Has narrative blocks but chunks is empty")

    # 5. Chunks in order (char_start non-decreasing)
    for i in range(len(chunks) - 1):
        if chunks[i]["char_start"] > chunks[i + 1]["char_start"]:
            errors.append(f"Chunks out of order: chunk {i} starts after chunk {i+1}")

    # 6. Unique id_chunk
    chunk_ids = [c["id_chunk"] for c in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        errors.append("Duplicate id_chunk values")

    # 7. id_chunk format
    for c in chunks:
        expected_prefix = f"{book_id}::chunk::"
        if not c["id_chunk"].startswith(expected_prefix):
            errors.append(f"Bad id_chunk format: {c['id_chunk']}")

    return errors


# ── Main ──────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("generate_chunks.py")
    print("=" * 60)

    tokenizer = _load_tokenizer()

    json_files = sorted(MASTER_DIR.glob("*.master.json"))
    print(f"\nProcesando {len(json_files)} archivos...\n")

    all_stats = []
    for fp in json_files:
        print(f"  {fp.name} ...", end=" ", flush=True)
        stats = process_file(fp, tokenizer)
        all_stats.append(stats)

        # Validate
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        errors = validate(data)
        status = "OK" if not errors else f"{len(errors)} ERROR(ES)"
        print(status)
        for e in errors:
            print(f"    ! {e}")

    # ── Report ────────────────────────────────────────────────────────
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("CHUNKING REPORT")
    report_lines.append("=" * 70)
    report_lines.append("")
    report_lines.append(f"Tokenizer: {tokenizer.name_or_path}")
    report_lines.append(f"MIN_SEARCH_TOKENS: {MIN_SEARCH_TOKENS}")
    report_lines.append(f"SOFT_MAX_TOKENS: {SOFT_MAX_TOKENS}")
    report_lines.append(f"HARD_MAX_TOKENS: {HARD_MAX_TOKENS}")
    report_lines.append(f"OVERLAP_TARGET_TOKENS: {OVERLAP_TARGET_TOKENS}")
    report_lines.append(f"OVERLAP_MIN_TOKENS: {OVERLAP_MIN_TOKENS}")
    report_lines.append(f"MIN_CHUNK_TOKENS: {MIN_CHUNK_TOKENS}")
    report_lines.append("")

    for s in all_stats:
        report_lines.append(f"--- {s['file']} ---")
        report_lines.append(f"  book_id:              {s['book_id']}")
        report_lines.append(f"  chunks generados:     {s['num_chunks']}")
        report_lines.append(f"  bloques narrativos:   {s['narr_blocks_used']}")
        report_lines.append(f"  bloques ignorados:    {s['blocks_ignored']}")
        report_lines.append(f"  avg tokens/chunk:     {s['avg_tokens']}")
        report_lines.append(f"  min tokens/chunk:     {s['min_tokens']}")
        report_lines.append(f"  max tokens/chunk:     {s['max_tokens']}")
        report_lines.append(f"  median tokens/chunk:  {s['median_tokens']}")
        report_lines.append(f"  avg chars/chunk:      {s['avg_chars']}")
        report_lines.append(f"  min chars/chunk:      {s['min_chars']}")
        report_lines.append(f"  max chars/chunk:      {s['max_chars']}")
        report_lines.append(f"  cortes duros:         {s['hard_cuts']}")
        report_lines.append(f"  chunks fusionados:    {s['merged_chunks']}")
        report_lines.append("")

    total_chunks = sum(s["num_chunks"] for s in all_stats)
    report_lines.append(f"TOTAL CHUNKS: {total_chunks}")
    report_lines.append(f"TOTAL FILES:  {len(all_stats)}")

    report_text = "\n".join(report_lines)

    report_path = MASTER_DIR / "chunking_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print("\n" + report_text)
    print(f"\nReporte guardado en: {report_path}")


if __name__ == "__main__":
    main()

