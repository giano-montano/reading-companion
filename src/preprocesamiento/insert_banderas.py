"""Insert BANDERA checkpoints into .master.json files.

Places pedagogical reading checkpoints after narrative blocks.
Spaces flags evenly across narrative blocks (~1 per 15-25 blocks).
Skips heading blocks. Respects is_narrative boundaries.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MASTER_DIR = ROOT / "data" / "master"
BACKUP_DIR = MASTER_DIR / "backup_before_banderas"


def make_bandera(book_id: str) -> dict:
    return {
        "id_block": "",
        "type": "BANDERA",
        "text": "--$CHECKPOINT_LECTURA$--",
        "chunk_id": None,
        "char_start": -1,
        "char_end": -1,
        "is_narrative": False,
    }


def is_heading(block: dict) -> bool:
    t = block.get("type", "")
    text = block.get("text", "").strip()
    return t in ("h1", "h2", "h3") and len(text) < 80


def process_book(original_data: dict) -> tuple[dict, int]:
    """Insert banderas into narrative islands, reindex IDs."""
    data = json.loads(json.dumps(original_data))
    book_id = data["book_id"]
    blocks = data["blocks"]

    # Build narrative islands (split only at is_narrative=false boundaries,
    # NOT at headings)
    islands: list[list[int]] = []
    current: list[int] = []

    for i, b in enumerate(blocks):
        if b["is_narrative"]:
            current.append(i)
        else:
            if current:
                islands.append(current)
                current = []
            islands.append([i])

    if current:
        islands.append(current)

    # Process each narrative island
    insertions: dict[int, list[dict]] = {}

    for island in islands:
        if not island or not blocks[island[0]]["is_narrative"]:
            continue

        n = len(island)
        if n == 0:
            continue

        # Find non-heading narrative blocks in this island
        candidates = []
        for rel_idx, abs_idx in enumerate(island):
            b = blocks[abs_idx]
            if not is_heading(b):
                text_len = len(b.get("text", ""))
                if text_len > 20:
                    candidates.append((rel_idx, abs_idx, text_len))

        if not candidates:
            continue

        # Target: number of flags based on island size
        if n < 100:
            target = max(3, n // 8)
        elif n < 500:
            target = n // 15
        elif n < 1500:
            target = n // 25
        else:
            target = n // 35

        target = min(target, len(candidates))  # can't exceed available candidates

        if target == 0:
            continue

        # Sort candidates by score (longer blocks first)
        candidates.sort(key=lambda x: -x[2])

        # Minimum gap between flags
        min_gap = max(3, len(candidates) // (target * 2 + 1)) if target > 0 else 3
        selected_rel = set()

        for rel_idx, abs_idx, _score in candidates:
            if len(selected_rel) >= target:
                break
            ok = True
            for s in selected_rel:
                if abs(rel_idx - s) < min_gap:
                    ok = False
                    break
            if ok:
                selected_rel.add(rel_idx)

        # If still not enough, relax min_gap
        if len(selected_rel) < target:
            for rel_idx, abs_idx, _score in candidates:
                if len(selected_rel) >= target:
                    break
                if rel_idx not in selected_rel:
                    ok = True
                    for s in selected_rel:
                        if abs(rel_idx - s) < 2:
                            ok = False
                            break
                    if ok:
                        selected_rel.add(rel_idx)

        for rel_idx in selected_rel:
            abs_idx = island[rel_idx]
            insertions.setdefault(abs_idx, []).append(make_bandera(book_id))

    # Build new blocks
    new_blocks: list[dict] = []
    flags_added = 0
    for i, b in enumerate(blocks):
        new_blocks.append(b)
        if i in insertions:
            for flag in insertions[i]:
                new_blocks.append(flag)
                flags_added += 1

    # Reindex IDs
    for idx, b in enumerate(new_blocks):
        b["id_block"] = f"{book_id}::block::{idx + 1}"

    data["blocks"] = new_blocks
    return data, flags_added


def main():
    json_files = sorted(MASTER_DIR.glob("*.master.json"))
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    changes_log: list[dict] = []
    print(f"Procesando {len(json_files)} archivos...\n")

    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f:
            original_text = f.read()

        # Save backup (raw original)
        backup_path = BACKUP_DIR / fp.name
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(original_text)

        original_data = json.loads(original_text)
        book_id = original_data["book_id"]
        orig_total = len(original_data["blocks"])
        narr_before = sum(1 for b in original_data["blocks"] if b["is_narrative"])
        non_narr_before = orig_total - narr_before

        modified_data, flags_added = process_book(original_data)
        final_total = len(modified_data["blocks"])
        non_narr_after = sum(1 for b in modified_data["blocks"] if not b["is_narrative"])

        with open(fp, "w", encoding="utf-8") as f:
            json.dump(modified_data, f, ensure_ascii=False, indent=2)
            f.write("\n")

        entry = {
            "archivo": fp.name,
            "book_id": book_id,
            "bloques_originales": orig_total,
            "bloques_finales": final_total,
            "bloques_narrativos": narr_before,
            "no_narrativos_antes": non_narr_before,
            "no_narrativos_despues": non_narr_after,
            "banderas_insertadas": flags_added,
        }
        changes_log.append(entry)

        print(f"  {fp.name}")
        print(f"    Bloques: {orig_total} -> {final_total}  (+{flags_added} banderas)")

    log_path = MASTER_DIR / "banderas_changes_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(changes_log, f, ensure_ascii=False, indent=2)
        f.write("\n")

    total_flags = sum(c["banderas_insertadas"] for c in changes_log)
    print(f"\nBackups originales: {BACKUP_DIR}")
    print(f"Log de cambios: {log_path}")
    print(f"Total banderas insertadas: {total_flags}")


if __name__ == "__main__":
    main()

