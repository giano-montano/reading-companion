"""
EpubBookLoader — load a book from an EPUB into a sequence of raw HTML blocks.

This is NOT a `CorpusLoader` (F1 `.txt` pipeline).  It produces a list of
`RawBlock` records; downstream components (checkpoints, splitting, writers)
turn them into a `BookMaster`.

Encoding strategy: try utf-8, fallback to latin-1 if the declared utf-8 decode
produces U+FFFD (the La Metamorfosis EPUB triggers this — declared utf-8 but
actually latin-1).
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass

import ebooklib
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

# Tags we keep in `content` (allowed per `data/master/master.md`).
_ALLOWED_TAGS = {"h1", "h2", "h3", "p", "blockquote", "hr", "nav"}
# Tags we strip but keep their text content.
_INNER_ONLY = {"span", "em", "strong", "b", "i", "a", "small", "sup", "sub"}
# Block-level discard (no useful text).
_DISCARD_TAGS = {"script", "style", "meta", "link"}

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


@dataclass
class RawBlock:
    """A block as it comes out of the EPUB, before sectioning and chunking."""
    id: int
    content: str   # small sanitized HTML
    text: str      # plain text used for token counting and chunk text
    is_narrative: bool  # True for <p>/<blockquote> with text; False for headers/hr/nav/empty


def _decode(raw: bytes) -> str:
    """Decode with declared-utf-8; if it produces U+FFFD, fallback to latin-1."""
    try:
        text = raw.decode("utf-8")
        if "\ufffd" in text:
            text = raw.decode("latin-1")
        return text
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _normalize_text(s: str) -> str:
    """Strip soft hyphens, NBSP, and collapse internal whitespace."""
    s = s.replace("\xad", "").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _html_for_element(el) -> str:
    """
    Return the small sanitized HTML fragment for a block-level element.

    Strategy: keep the element itself if it's an allowed block tag, with its
    full inner content.  Inline tags allowed per `data/master/master.md`
    (`em`, `strong`, `br`, etc.) are preserved as-is; other inline tags are
    unwrapped (kept their text).  `<hr>` and empty `<p>` are emitted as-is
    when applicable.
    """
    name = (el.name or "").lower()
    if name == "hr":
        return "<hr/>"
    if name in {"h1", "h2", "h3", "blockquote", "p", "nav"}:
        # Walk children, dropping tags not in allowed/inline, unwrapping their
        # text content.
        cleaned: list[str] = []
        for child in el.children:
            if getattr(child, "name", None) is None:
                cleaned.append(str(child))
                continue
            tag = child.name.lower()
            if tag in _ALLOWED_TAGS or tag in _INNER_ONLY:
                cleaned.append(str(child))
            else:
                # unwrap: keep text descendants
                for sub in child.descendants:
                    if getattr(sub, "name", None) is None:
                        cleaned.append(str(sub))
        inner = "".join(cleaned).strip()
        if not inner:
            return ""
        return f"<{name}>{inner}</{name}>"
    return ""


def _is_narrative(name: str, text: str) -> bool:
    if name in {"p", "blockquote"} and text:
        return True
    return False


class EpubBookLoader:
    """
    Walk the EPUB spine in order, producing a list of `RawBlock` per book.

    A block is a single block-level element: `<h1>`, `<h2>`, `<h3>`,
    `<blockquote>`, `<hr>`, `<nav>`, or `<p>`.  Empty `<p>` and decorative
    spans are dropped.
    """

    def __init__(self, epub_path: str) -> None:
        self._path = epub_path

    def load(self) -> tuple[str, list[RawBlock]]:
        book = epub.read_epub(self._path)

        title = ""
        creator = ""
        year: int | None = None
        language: str | None = None
        meta = book.get_metadata("DC", "title")
        if meta:
            title = str(meta[0][0])
        meta = book.get_metadata("DC", "creator")
        if meta:
            creator = str(meta[0][0])
        meta = book.get_metadata("DC", "date")
        if meta:
            m = re.search(r"(\d{4})", str(meta[0][0]))
            if m:
                year = int(m.group(1))
        meta = book.get_metadata("DC", "language")
        if meta:
            language = str(meta[0][0])

        header = f"{title}|{creator}|{year}|{language}"

        blocks: list[RawBlock] = []
        next_id = 1
        for spine_entry in book.spine:
            item_id = spine_entry[0]
            item = book.get_item_with_id(item_id)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            raw = item.get_content() or b""
            text = _decode(raw)
            soup = BeautifulSoup(text, "html.parser")

            for el in soup.find_all(list(_ALLOWED_TAGS)):
                if el.name in _DISCARD_TAGS:
                    continue
                if el.name == "p" and not el.get_text(strip=True):
                    continue
                fragment = _html_for_element(el)
                if not fragment:
                    continue
                plain = _normalize_text(el.get_text(" ", strip=True))
                if not plain and el.name != "hr":
                    continue
                blocks.append(
                    RawBlock(
                        id=next_id,
                        content=fragment,
                        text=plain,
                        is_narrative=_is_narrative(el.name, plain),
                    )
                )
                next_id += 1

        return header, blocks
