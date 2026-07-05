"""
NarrativeChunker — group narrative blocks into retrieval-sized chunks.

Strategy (per `data/master/master.md` §"Estrategia de chunking"):

  1. Walk narrative blocks in reading order, by section.
  2. Accumulate whole blocks into the current chunk.
  3. Close on a natural boundary (end of <p>/<blockquote>) when the chunk
     is at or above `target_tokens`.
  4. Allow up to `max_flexible_tokens` to avoid a too-small tail.
  5. NEVER close a chunk just because a checkpoint appeared; chunks may
     cross section boundaries.
  6. If a single block exceeds `max_flexible_tokens`, split it by sentence
     (or by dialogue turn) BEFORE adding it.
  7. No persistent overlap.

The chunker reads only the blocks of the master and writes back the chunks'
`char_start` / `char_end` and the blocks' `chunk_id`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from companion.corpus.book_master import BookBlock, BookChunk, BookMaster
from companion.corpus.canonical_text import _token_count

# Approx sentence boundary; used only when a single block is oversized.
_SENTENCE_SPLIT = re.compile(r"(?<=[\.\?\!])\s+")
# Dialogue turn: lines that begin with a dash and a capital letter (Spanish
# typography for direct speech).
_DIALOGUE_TURN = re.compile(r"\n\s*[—–-]\s*[A-ZÁÉÍÓÚÑ¿¡]")


@dataclass
class ChunkerParams:
    target_tokens: int = 270
    min_tokens: int = 100
    max_tokens: int = 400
    max_flexible_tokens: int = 500

    def __post_init__(self) -> None:
        if not (self.min_tokens <= self.target_tokens <= self.max_tokens <= self.max_flexible_tokens):
            raise ValueError(
                "params must satisfy min <= target <= max <= max_flexible; got "
                f"{self.min_tokens}/{self.target_tokens}/{self.max_tokens}/{self.max_flexible_tokens}"
            )


class NarrativeChunker:
    def __init__(
        self,
        target_tokens: int = 270,
        min_tokens: int = 100,
        max_tokens: int = 400,
        max_flexible_tokens: int = 500,
    ) -> None:
        self.params = ChunkerParams(
            target_tokens=target_tokens,
            min_tokens=min_tokens,
            max_tokens=max_tokens,
            max_flexible_tokens=max_flexible_tokens,
        )

    def chunk(self, master: BookMaster) -> BookMaster:
        narrative = [b for b in master.blocks if b.is_narrative]
        if not narrative:
            master.chunks = []
            for b in master.blocks:
                b.chunk_id = None
            return master

        # Each unit is either a whole block, or a piece of an oversized block.
        # For oversized blocks we mark `is_oversized_piece=True` so the chunker
        # doesn't merge their pieces into an existing chunk — each piece is
        # emitted on its own boundary.
        units: list[tuple[BookBlock, bool]] = []
        for b in narrative:
            if _token_count(b.text) > self.params.max_flexible_tokens:
                pieces = self._split_oversized(b)
                for p in pieces:
                    units.append((p, True))
            else:
                units.append((b, False))

        chunks: list[BookChunk] = []
        current: list[BookBlock] = []
        chunk_id = 1

        def flush() -> BookChunk | None:
            nonlocal current, chunk_id
            if not current:
                return None
            section_ids = _ordered_sections(current)
            text = _join_text(current)
            chunk = BookChunk(
                id=chunk_id,
                section_ids=section_ids,
                start_block_id=current[0].id,
                end_block_id=current[-1].id,
                text=text,
                char_start=0,  # filled by canonical_text.recompute_offsets
                char_end=0,
                token_count=_token_count(text),
            )
            chunks.append(chunk)
            chunk_id += 1
            current = []
            return chunk

        for unit, is_oversized_piece in units:
            unit_tokens = _token_count(unit.text)
            if is_oversized_piece:
                # Always flush before an oversized piece and never merge into it.
                if current:
                    flush()
                current.append(unit)
                # If the piece itself exceeds the hard cap, close it as a chunk
                # on its own (rare; the splitter should have prevented this).
                if unit_tokens >= self.params.max_flexible_tokens:
                    flush()
                continue
            if not current:
                current.append(unit)
                continue
            current_tokens = _token_count(_join_text(current))
            projected = current_tokens + unit_tokens
            # Would adding this unit exceed the hard cap?  Close first.
            if projected > self.params.max_flexible_tokens and current_tokens >= self.params.min_tokens:
                flush()
                current.append(unit)
                continue
            # Would adding push us past the soft max, and we already have enough?
            if projected > self.params.max_tokens and current_tokens >= self.params.min_tokens:
                flush()
                current.append(unit)
                continue
            # Would adding push us past the target, and we already have a
            # reasonable chunk?  Close to keep chunks near the target.
            if projected > self.params.target_tokens and current_tokens >= self.params.min_tokens:
                flush()
                current.append(unit)
                continue
            # Otherwise accumulate.
            current.append(unit)

        # Tail: close it, but if it's too small, fold it into the previous chunk
        # ONLY if the previous chunk has room (not over the soft max).
        if current:
            tail_tokens = _token_count(_join_text(current))
            prev = chunks[-1] if chunks else None
            if prev is not None and tail_tokens < self.params.min_tokens \
                    and prev.token_count < self.params.max_tokens:
                tail_text = _join_text(current)
                prev.text = prev.text + "\n\n" + tail_text
                prev.end_block_id = current[-1].id
                prev.section_ids = _ordered_sections(
                    [b for b in master.blocks if prev.start_block_id <= b.id <= prev.end_block_id]
                )
                prev.token_count = _token_count(prev.text)
            else:
                flush()

        master.chunks = chunks
        block_to_chunk: dict[int, int] = {}
        for c in chunks:
            for b in master.blocks:
                if c.start_block_id <= b.id <= c.end_block_id and b.is_narrative:
                    block_to_chunk.setdefault(b.id, c.id)
        for b in master.blocks:
            b.chunk_id = block_to_chunk.get(b.id)
        return master

    # -- internals ----------------------------------------------------------

    def _split_oversized(self, block: BookBlock) -> list[BookBlock]:
        """
        A narrative block whose text exceeds `max_flexible_tokens` is split
        by sentence (or dialogue turn) into multiple `BookBlock`s, all
        sharing the same id (the caller will treat them as one block_unit).
        Here we re-id them sequentially to keep them distinguishable within
        the chunker, and the master keeps the original id (the chunker only
        sees internal units).
        """
        text = block.text
        # Prefer dialogue turn splits if the block has many line-broken
        # dialogue turns (heuristic: at least 3 turns).  Otherwise split by
        # sentence boundary.
        dialogue_turns = _DIALOGUE_TURN.findall(text)
        if len(dialogue_turns) >= 3:
            parts = _DIALOGUE_TURN.split(text)
        else:
            parts = _SENTENCE_SPLIT.split(text)
        parts = [p.strip() for p in parts if p and p.strip()]
        if len(parts) <= 1:
            return [block]
        out: list[BookBlock] = []
        for i, p in enumerate(parts):
            out.append(
                BookBlock(
                    id=block.id,
                    content=block.content,  # best-effort: keep original HTML
                    text=p,
                    is_narrative=True,
                )
            )
        return out


def _ordered_sections(blocks: list[BookBlock]) -> list[int]:
    seen: list[int] = []
    for b in blocks:
        if b.section_id is not None and b.section_id not in seen:
            seen.append(b.section_id)
    return seen


def _join_text(blocks: list[BookBlock]) -> str:
    return "\n\n".join(b.text for b in blocks if b.text)
