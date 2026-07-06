"""
CLI: `python -m companion.cli.preprocess <epub_filename> --book-id <id> [flags]`

Reads the EPUB from `data/source/<epub_filename>`, runs the full book
preprocessing pipeline, and writes the three artifacts under `data/`
using the FLAT layout (see `data/estructura.md`):

  data/master/<book_id>.master.json
  data/outputs/readers/<book_id>/reader.json
  data/outputs/retrievals/<book_id>/retrieval.jsonl

Sections (pausas pedagógicas) are MANUAL.  The default
(`--checkpoints=none`) produces a master with `sections: []` and every
`block.section_id = null`.  Use `--checkpoints=json` with a hand-curated
`checkpoints.json` to mark the real pausas.

`--year` always wins over the EPUB's DC date.  If neither is given, the
script aborts with an error — never guesses a publication year.

Examples:

  # default: no sections, year from the EPUB
  python -m companion.cli.preprocess La_Metamorfosis-Kafka_Franz.epub \\
      --book-id la_metamorfosis_es

  # with manual year and manual pausas
  python -m companion.cli.preprocess La_Metamorfosis-Kafka_Franz.epub \\
      --book-id la_metamorfosis_es \\
      --year 1915 \\
      --checkpoints=json --checkpoints-json=data/master/la_metamorfosis_es.checkpoints.json

  # exploration only: heuristic pausas (warning emitted)
  python -m companion.cli.preprocess La_Metamorfosis-Kafka_Franz.epub \\
      --book-id la_metamorfosis_es --checkpoints=heuristic
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from companion.chunkers.narrative import NarrativeChunker
from companion.corpus.book_builder import build_book
from companion.corpus.checkpoints import (
    HeuristicCheckpointResolver,
    JsonCheckpointResolver,
)

logger = logging.getLogger(__name__)


def _resolve_epub_path(filename: str, data_dir: str) -> Path:
    """If `filename` is absolute, return it; otherwise look under data_dir/source/."""
    p = Path(filename)
    if p.is_absolute():
        return p
    candidate = Path(data_dir) / "source" / filename
    if candidate.exists():
        return candidate
    if p.exists():
        return p
    raise FileNotFoundError(
        f"EPUB not found. Tried:\n  - {candidate}\n  - {p}\n"
        f"Pass an absolute path or a file under {data_dir}/source/."
    )


def _read_dc_metadata(epub_path: str) -> dict[str, object]:
    from ebooklib import epub

    book = epub.read_epub(epub_path)
    out: dict[str, object] = {}

    title = book.get_metadata("DC", "title")
    if title:
        out["title"] = str(title[0][0])
    creator = book.get_metadata("DC", "creator")
    if creator:
        out["author"] = str(creator[0][0])
    date = book.get_metadata("DC", "date")
    if date:
        m = re.search(r"(\d{4})", str(date[0][0]))
        if m:
            out["year"] = int(m.group(1))
    lang = book.get_metadata("DC", "language")
    if lang:
        out["language"] = str(lang[0][0])
    return out


def _validate_year(year: int | None, source: str) -> int | None:
    """Reject years outside a sane range; return None if input is None."""
    if year is None:
        return None
    current_year = datetime.now().year
    if year < 1000 or year > current_year + 1:
        raise ValueError(
            f"year {year} (from {source}) is outside the sane range "
            f"[1000, {current_year + 1}]. Pass --year to override."
        )
    return year


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="companion preprocess",
        description=(
            "Preprocess an EPUB into master.json + reader.json + retrieval.jsonl. "
            "Sections (pausas pedagógicas) are MANUAL by default."
        ),
    )
    p.add_argument(
        "epub",
        help=(
            "EPUB filename.  Resolved against <data-dir>/source/ if not absolute. "
            "Example: 'La_Metamorfosis-Kafka_Franz.epub'"
        ),
    )
    p.add_argument("--book-id", required=True, help="Stable snake_case id for the book.")
    p.add_argument(
        "--data-dir",
        default="data",
        help="Root of the data/ tree.  Default: 'data'.",
    )
    p.add_argument("--title", default=None, help="Override the book title.")
    p.add_argument("--author", default=None, help="Override the author.")
    p.add_argument(
        "--year",
        type=int,
        default=None,
        help=(
            "Publication year.  If given, ALWAYS wins over the EPUB's DC date. "
            "If neither is set, the script aborts."
        ),
    )
    p.add_argument("--language", default=None, help="Override language code.")

    p.add_argument(
        "--checkpoints",
        choices=("none", "heuristic", "json"),
        default="none",
        help=(
            "How to mark pausas pedagógicas.  'none' (default) leaves every "
            "block.section_id = null.  'json' loads a hand-curated "
            "checkpoints.json.  'heuristic' is for exploration only and "
            "emits a warning."
        ),
    )
    p.add_argument(
        "--checkpoints-json",
        default=None,
        help="Path to checkpoints.json (used when --checkpoints=json).",
    )

    p.add_argument("--chunk-target", type=int, default=270, help="Target tokens per chunk.")
    p.add_argument("--chunk-min", type=int, default=100, help="Minimum tokens per chunk.")
    p.add_argument("--chunk-max", type=int, default=400, help="Soft maximum tokens per chunk.")
    p.add_argument(
        "--chunk-max-flex",
        type=int,
        default=500,
        help="Hard maximum; blocks larger than this are split by sentence.",
    )

    p.add_argument(
        "--questions-per-chunk",
        type=int,
        default=5,
        help="Number of hypothetical questions to generate per chunk.",
    )

    p.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        epub_path = _resolve_epub_path(args.epub, args.data_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    dc = _read_dc_metadata(str(epub_path))
    title = args.title or dc.get("title")
    author = args.author or dc.get("author")
    language = args.language or dc.get("language")

    # --year always wins.  Fall back to DC year if it's sane.  Else error.
    try:
        if args.year is not None:
            year: int | None = _validate_year(args.year, "--year CLI flag")
        elif "year" in dc:
            year = _validate_year(dc["year"], "EPUB DC date")  # type: ignore[arg-type]
        else:
            year = None
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if year is None:
        print(
            "ERROR: could not determine the publication year. "
            "Pass --year (ej: --year 1915).",
            file=sys.stderr,
        )
        return 2

    if not title or not author:
        print(
            "ERROR: book metadata incomplete (need title and author). "
            "Pass --title and --author or use a richer EPUB.",
            file=sys.stderr,
        )
        return 2

    if args.checkpoints == "json":
        if not args.checkpoints_json:
            print("ERROR: --checkpoints=json requires --checkpoints-json", file=sys.stderr)
            return 2
        resolver = JsonCheckpointResolver(args.checkpoints_json)
    elif args.checkpoints == "heuristic":
        resolver = HeuristicCheckpointResolver()
    else:
        resolver = None  # no sections; manual later

    chunker = NarrativeChunker(
        target_tokens=args.chunk_target,
        min_tokens=args.chunk_min,
        max_tokens=args.chunk_max,
        max_flexible_tokens=args.chunk_max_flex,
    )

    result = build_book(
        epub_path=str(epub_path),
        book_id=args.book_id,
        data_dir=args.data_dir,
        title=str(title),
        author=str(author),
        year=year,
        language=str(language) if language else None,
        checkpoints=resolver,
        chunker=chunker,
        questions_per_chunk=args.questions_per_chunk,
    )

    print()
    print("OK")
    print(f"  book_id           : {result.book_id}")
    print(f"  blocks (total)    : {result.n_blocks}")
    print(f"  narrative blocks  : {result.n_narrative_blocks}")
    print(f"  sections          : {result.n_sections}")
    print(f"  chunks            : {result.n_chunks}")
    print(f"  master            : {result.master_path}")
    print(f"  reader            : {result.reader_path}")
    print(f"  retrieval         : {result.retrieval_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
