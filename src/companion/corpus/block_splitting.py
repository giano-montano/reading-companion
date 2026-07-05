"""
Block splitting — when a checkpoint falls INSIDE a narrative block, split it.

Per `data/master/master.md` §"Reglas de secciones": if a checkpoint is in the
middle of a paragraph, the block must be divided before sections are assigned.
This module only splits a block's *content* and *text*; section assignment
is done by `checkpoints.assign_section_ids` afterwards.

Heuristic: split a <p> at the first sentence boundary (". ", "? ", "! ") that
appears at or after the requested split point, then re-validate the new
fragments have HTML balanced.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from companion.corpus.epub_loader import RawBlock

_SENTENCE_BOUNDARY = re.compile(r"(?<=[\.\?\!])\s")


@dataclass
class SplitResult:
    before: RawBlock
    after: RawBlock


def split_block_at(block: RawBlock, split_offset: int) -> SplitResult | None:
    """
    Attempt to split `block` so that the first `split_offset` characters of
    `text` end up in `before` and the rest in `after`.

    Returns `None` if the block cannot be split cleanly (caller may skip).
    """
    text = block.text
    if split_offset <= 0 or split_offset >= len(text):
        return None

    # Find the next sentence boundary at or after split_offset
    m = _SENTENCE_BOUNDARY.search(text, split_offset)
    if m is None:
        # fallback: any whitespace
        m = re.search(r"\s", text[split_offset:])
        if m is None:
            return None
        cut = split_offset + m.start()
    else:
        cut = m.end()  # after the whitespace, start of new sentence

    before_text = text[:cut].rstrip()
    after_text = text[cut:].lstrip()
    if not before_text or not after_text:
        return None

    before_content = _split_html_at(block.content, cut_in_text=cut, total_text_len=len(text))
    after_content = _split_html_at(
        block.content, cut_in_text=cut, total_text_len=len(text), keep_tail=True
    )
    if before_content is None or after_content is None:
        return None

    before = RawBlock(
        id=block.id,
        content=before_content,
        text=before_text,
        is_narrative=block.is_narrative and bool(before_text),
    )
    after = RawBlock(
        id=block.id,  # same id; caller must renumber
        content=after_content,
        text=after_text,
        is_narrative=block.is_narrative and bool(after_text),
    )
    return SplitResult(before=before, after=after)


def _split_html_at(html: str, cut_in_text: int, total_text_len: int, keep_tail: bool = False) -> str | None:
    """
    Naive HTML splitter: walk the HTML character-by-character, tracking the
    text-length accumulated from text nodes.  When we reach `cut_in_text`,
    close the current open tag in the head fragment, and reopen it for the
    tail fragment.  If the tag structure is too complex, return None.
    """
    head: list[str] = []
    tail: list[str] = []
    text_pos = 0
    i = 0
    open_stack: list[str] = []
    in_tag = False
    buf: list[str] = []
    cut_done = False

    def emit(s: str) -> None:
        if not cut_done:
            head.append(s)
        else:
            tail.append(s)

    while i < len(html):
        ch = html[i]
        if ch == "<":
            # flush any text buffer
            if buf and not cut_done:
                head.append("".join(buf))
                buf = []
            elif buf and cut_done:
                tail.append("".join(buf))
                buf = []
            in_tag = True
            tag_buf: list[str] = [ch]
            i += 1
            while i < len(html) and html[i] != ">":
                tag_buf.append(html[i])
                i += 1
            if i < len(html):
                tag_buf.append(html[i])
                i += 1
            tag = "".join(tag_buf)
            emit(tag)
            # track open/close
            stripped = tag.strip()
            if stripped.startswith("</"):
                if open_stack:
                    open_stack.pop()
            elif not stripped.endswith("/>") and not stripped.lower().startswith("<br") \
                    and not stripped.lower().startswith("<hr"):
                m = re.match(r"<([a-zA-Z0-9]+)", stripped)
                if m:
                    open_stack.append(m.group(1).lower())
            in_tag = False
            continue

        if not cut_done:
            head.append(ch)
        else:
            tail.append(ch)
        # count toward text length only outside tags
        if not in_tag:
            text_pos += 1
            if not cut_done and text_pos >= cut_in_text:
                # close the open stack in the head, reopen in the tail
                for tag in reversed(open_stack):
                    head.append(f"</{tag}>")
                for tag in open_stack:
                    tail.append(f"<{tag}>")
                cut_done = True
        i += 1

    # flush trailing text buf
    if buf:
        if cut_done:
            tail.append("".join(buf))
        else:
            head.append("".join(buf))

    head_html = "".join(head).strip()
    tail_html = "".join(tail).strip()
    if not head_html or not tail_html:
        return None
    return head_html if not keep_tail else tail_html
