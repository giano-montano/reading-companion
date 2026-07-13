from __future__ import annotations

import argparse
import json
import re
import unicodedata
import warnings
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

TEXT_TAGS = {"h1", "h2", "h3", "p"}
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "source"
OUTPUT_DIR = PROJECT_ROOT / "data" / "master"

TAG_TO_TYPE = {
    "h1": "h1",
    "h2": "h2",
    "h3": "h3",
    "p": "p",
}


def decode_content(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8")
        if "\ufffd" in text:
            text = raw.decode("latin-1")
        return text
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def normalize_text(text: str) -> str:
    text = text.replace("\xad", "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(char for char in nfkd if not unicodedata.combining(char))


def slugify(text: str) -> str:
    text = strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text


def make_book_id(
    title: str | None,
    author: str | None,
    epub_path: Path,
) -> str:
    parts: list[str] = []

    if title:
        parts.append(title)

    if author:
        parts.append(author)

    if not parts:
        parts.append(epub_path.stem)

    base = slugify(" ".join(parts))

    if not base:
        base = "unknown_book"

    return base


def extract_first_metadata_value(
    book: epub.EpubBook,
    namespace: str,
    key: str,
) -> str | None:
    metadata = book.get_metadata(namespace, key)

    if not metadata:
        return None

    value = str(metadata[0][0]).strip()

    if not value:
        return None

    return value


def extract_publication_year(book: epub.EpubBook) -> int | None:
    raw_date = extract_first_metadata_value(book, "DC", "date")

    if not raw_date:
        return None

    match = re.search(r"(\d{4})", raw_date)

    if not match:
        return None

    return int(match.group(1))


def extract_blocks_from_epub(book: epub.EpubBook) -> list[tuple[str, str]]:
    raw_blocks: list[tuple[str, str]] = []

    for spine_entry in book.spine:
        item_id = spine_entry[0]
        item = book.get_item_with_id(item_id)

        if item is None:
            continue

        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        raw = item.get_content() or b""
        html = decode_content(raw)

        soup = BeautifulSoup(html, "html.parser")

        for element in soup.find_all(list(TEXT_TAGS)):
            tag = (element.name or "").lower()

            if tag not in TEXT_TAGS:
                continue

            text = normalize_text(element.get_text(" ", strip=True))

            if not text:
                continue

            raw_blocks.append((tag, text))

    return raw_blocks


def build_master_from_epub(epub_path: Path) -> dict:
    book = epub.read_epub(str(epub_path))

    title = extract_first_metadata_value(book, "DC", "title")
    author = extract_first_metadata_value(book, "DC", "creator")
    publication_year = extract_publication_year(book)

    book_id = make_book_id(
        title=title,
        author=author,
        epub_path=epub_path,
    )

    raw_blocks = extract_blocks_from_epub(book)

    blocks: list[dict] = []
    cursor = 0

    for i, (tag, text) in enumerate(raw_blocks, start=1):
        block_type = TAG_TO_TYPE[tag]

        char_start = cursor
        char_end = cursor + len(text)

        blocks.append(
            {
                "id_block": f"{book_id}::block::{i}",
                "type": block_type,
                "text": text,
                "chunk_id": None,
                "char_start": char_start,
                "char_end": char_end,
                "is_narrative": True,
            }
        )

        cursor = char_end + 2

    master = {
        "book_id": book_id,
        "metadata": {
            "title": title,
            "author": author,
            "publication_year": publication_year,
        },
        "blocks": blocks,
        "chunks": [],
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    out_path = OUTPUT_DIR / f"{book_id}.master.json"
    out_path.write_text(
        json.dumps(master, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "epub_filename": epub_path.name,
        "book_id": book_id,
        "title": title,
        "author": author,
        "publication_year": publication_year,
        "blocks": len(blocks),
        "out_path": str(out_path),
    }


def build_masters_from_directory() -> list[dict]:
    epub_paths = sorted(INPUT_DIR.glob("*.epub"))

    if not epub_paths:
        raise FileNotFoundError(f"No se encontraron archivos .epub en: {INPUT_DIR}")

    results: list[dict] = []

    for epub_path in epub_paths:
        print(f"Procesando {epub_path.name} ...")

        try:
            result = build_master_from_epub(epub_path)
            results.append(result)

            print(
                f"  -> {result['book_id']}: "
                f"{result['blocks']} bloques -> "
                f"{Path(result['out_path']).name}"
            )

        except Exception as error:
            print(f"  ERROR procesando {epub_path.name}: {error}")

    summary_path = OUTPUT_DIR / "masters_summary.json"
    summary_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Resumen escrito en: {summary_path}")

    return results


def main() -> None:
    build_masters_from_directory()


if __name__ == "__main__":
    main()