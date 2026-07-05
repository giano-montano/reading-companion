"""
CLI: `python -m companion.cli.preprocess <epub> --book-id <id> [flags]`

Runs the full book-preprocessing pipeline and writes the three artifacts
under `data/books/<book_id>/`.

Default metadata (title, author, year, language) is read from the EPUB's DC
metadata and can be overridden via flags.  If DC metadata is missing or
incomplete, supply `--title` and `--author` (otherwise the script aborts).

Examples:

  python -m companion.cli.preprocess \\
      data/source/La_Metamorfosis-Kafka_Franz.epub \\
      --book-id la_metamorfosis_es

  python -m companion.cli.preprocess book.epub --book-id foo \\
      --checkpoints=json --checkpoints-json=checkpoints.json \\
      --no-split-blocks \\
      --chunk-target=300 --chunk-max=450
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from companion.chunkers.narrative import NarrativeChunker
from companion.corpus.book_builder import build_book
from companion.corpus.checkpoints import HeuristicCheckpointResolver, JsonCheckpointResolver


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
        import re
        m = re.search(r"(\d{4})", str(date[0][0]))
        if m:
            out["year"] = int(m.group(1))
    lang = book.get_metadata("DC", "language")
    if lang:
        out["language"] = str(lang[0][0])
    return out


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="companion preprocess",
        description="Preprocess an EPUB into master.json + reader.json + retrieval.jsonl.",
    )
    p.add_argument("epub", help="Path to the source EPUB.")
    p.add_argument("--book-id", required=True, help="Stable snake_case id for the book.")
    p.add_argument(
        "--out-dir",
        default=None,
        help="Output root.  Default: data/books/<book_id>/",
    )
    p.add_argument("--title", default=None, help="Override the book title.")
    p.add_argument("--author", default=None, help="Override the author.")
    p.add_argument("--year", type=int, default=None, help="Override publication year.")
    p.add_argument("--language", default=None, help="Override language code.")

    p.add_argument(
        "--checkpoints",
        choices=("heuristic", "json"),
        default="heuristic",
        help="Checkpoint resolver to use.",
    )
    p.add_argument(
        "--checkpoints-json",
        default=None,
        help="Path to checkpoints.json (used when --checkpoints=json).",
    )
    p.add_argument(
        "--no-split-blocks",
        action="store_true",
        help="Disable block splitting (default: split when needed).",
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

    epub_path = args.epub
    if not Path(epub_path).exists():
        print(f"ERROR: EPUB not found: {epub_path}", file=sys.stderr)
        return 2

    out_dir = args.out_dir or f"data/books/{args.book_id}"

    dc = _read_dc_metadata(epub_path)
    title = args.title or dc.get("title")
    author = args.author or dc.get("author")
    year = args.year if args.year is not None else dc.get("year")
    language = args.language or dc.get("language")
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
    else:
        resolver = HeuristicCheckpointResolver()

    chunker = NarrativeChunker(
        target_tokens=args.chunk_target,
        min_tokens=args.chunk_min,
        max_tokens=args.chunk_max,
        max_flexible_tokens=args.chunk_max_flex,
    )

    result = build_book(
        epub_path=epub_path,
        book_id=args.book_id,
        out_dir=out_dir,
        title=str(title),
        author=str(author),
        year=year if isinstance(year, int) else None,  # type: ignore[arg-type]
        language=str(language) if language else None,
        checkpoints=resolver,
        split_blocks=not args.no_split_blocks,
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
