"""
insert_hypotheticals.py — Inserta preguntas hipotéticas en los retrieval.jsonl.

Lee los archivos data/outputs/hypotheticals/<book_id>.hypotheticals.jsonl
y actualiza el campo metadata.hypothetical_questions en los archivos
data/outputs/retrieval/<book_id>.retrieval.jsonl correspondientes.

Uso:
  .venv\\Scripts\\python.exe -m preprocesamiento.insert_hypotheticals --all
  .venv\\Scripts\\python.exe -m preprocesamiento.insert_hypotheticals --book_id el_viejo_y_el_mar_ernest_hemingway
  .venv\\Scripts\\python.exe -m preprocesamiento.insert_hypotheticals --list
  .venv\\Scripts\\python.exe -m preprocesamiento.insert_hypotheticals --all --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RETRIEVAL_DIR = ROOT / "data" / "outputs" / "retrieval"
HYPOTHETICALS_DIR = ROOT / "data" / "outputs" / "hypotheticals"


def load_questions(path: Path) -> dict[str, list[str]]:
    """Load hypothetical questions from a JSONL file into a chunk_id -> questions map."""
    questions: dict[str, list[str]] = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            cid = entry.get("chunk_id", "")
            qs = entry.get("hypothetical_questions", [])
            if cid and qs:
                questions[cid] = qs
    return questions


def insert_questions(
    retrieval_path: Path,
    questions_path: Path,
    dry_run: bool = False,
) -> int:
    """Insert questions into a retrieval JSONL file. Returns count of updated chunks."""
    if not questions_path.exists():
        print(f"  WARN: no encontrado {questions_path}", file=sys.stderr)
        return 0

    questions = load_questions(questions_path)
    if not questions:
        print(f"  WARN: sin preguntas en {questions_path}", file=sys.stderr)
        return 0

    with open(retrieval_path, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    updated = 0
    for entry in lines:
        cid = entry.get("chunk_id", "")
        if cid in questions:
            entry["metadata"]["hypothetical_questions"] = questions[cid]
            updated += 1

    if dry_run:
        return updated

    with open(retrieval_path, "w", encoding="utf-8") as f:
        for entry in lines:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inserta preguntas hipotéticas en retrieval.jsonl"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book_id", type=str, help="ID del libro")
    group.add_argument("--all", action="store_true", help="Procesar todos los libros")
    group.add_argument("--list", action="store_true", help="Listar archivos de hypotheticals")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar sin escribir")
    args = parser.parse_args()

    if args.list:
        hypos = sorted(HYPOTHETICALS_DIR.glob("*.hypotheticals.jsonl"))
        if not hypos:
            print("No hay archivos hypotheticals", file=sys.stderr)
            return
        for hp in hypos:
            with open(hp, "r", encoding="utf-8") as f:
                count = sum(1 for line in f if line.strip())
            book_id = hp.stem.replace(".hypotheticals", "")
            print(f"  {book_id}: {count} chunks")
        return

    if args.all:
        hypos = sorted(HYPOTHETICALS_DIR.glob("*.hypotheticals.jsonl"))
        if not hypos:
            print("No hay archivos hypotheticals", file=sys.stderr)
            sys.exit(1)
        book_ids = [hp.stem.replace(".hypotheticals", "") for hp in hypos]
    else:
        book_ids = [args.book_id]

    total_updated = 0
    for book_id in book_ids:
        rpath = RETRIEVAL_DIR / f"{book_id}.retrieval.jsonl"
        hpath = HYPOTHETICALS_DIR / f"{book_id}.hypotheticals.jsonl"

        if not rpath.exists():
            print(f"  SKIP: {rpath} no encontrado", file=sys.stderr)
            continue

        action = "[dry-run]" if args.dry_run else "actualizado"
        n = insert_questions(rpath, hpath, dry_run=args.dry_run)
        print(f"  {book_id}: {n} chunks {action}")
        total_updated += n

    print(f"Total: {total_updated} chunks")


if __name__ == "__main__":
    main()
