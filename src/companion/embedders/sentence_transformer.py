from __future__ import annotations

from companion.embedders.base import Embedder

QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "
MAX_SEQ_LENGTH = 512


class SentenceTransformerEmbedder(Embedder):
    """Local embedding via sentence-transformers with E5 prefix convention.

    - embed()      → prepends "query: "  (for retrieval queries)
    - embed_batch() → prepends "passage: " (for indexing chunks)

    Texts longer than 512 tokens are split into overlapping segments,
    embedded separately, and averaged (mean pooling) so no content is lost.
    """

    def __init__(self, model_name: str = "intfloat/multilingual-e5-base") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError("pip install sentence-transformers") from exc
        self._model = SentenceTransformer(model_name)
        self._model.max_seq_length = MAX_SEQ_LENGTH
        self._dim: int = (
            self._model.get_embedding_dimension()
            if hasattr(self._model, "get_embedding_dimension")
            else self._model.get_sentence_embedding_dimension()
        )

    def embed(self, text: str) -> list[float]:
        """Embed a query (prepends 'query: '). Queries are short, no chunking needed."""
        return self._model.encode(
            QUERY_PREFIX + text,
            convert_to_numpy=True,
        ).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed passages for indexing (prepends 'passage: ').

        Passages longer than MAX_SEQ_LENGTH tokens are split into segments,
        each segment is embedded separately, and the result is the element-wise
        mean of all segment vectors.
        """
        results: list[list[float]] = []
        tokenizer = self._model.tokenizer

        for text in texts:
            prefixed = PASSAGE_PREFIX + text
            tokens = tokenizer.encode(prefixed)

            if len(tokens) <= MAX_SEQ_LENGTH:
                vec = self._model.encode(
                    prefixed, convert_to_numpy=True,
                ).tolist()
                results.append(vec)
                continue

            # Mean pooling over segments
            segments = _split_tokens(tokens, MAX_SEQ_LENGTH)
            segment_texts = [
                tokenizer.decode(seg, skip_special_tokens=True)
                for seg in segments
            ]
            embeddings = self._model.encode(
                segment_texts,
                convert_to_numpy=True,
                batch_size=min(8, len(segment_texts)),
                show_progress_bar=False,
            )
            # Average across segments
            import numpy as np
            results.append(np.mean(embeddings, axis=0).tolist())

        return results

    @property
    def dimension(self) -> int:
        return self._dim


def _split_tokens(tokens: list[int], max_len: int) -> list[list[int]]:
    """Split a long token list into overlapping segments of max_len.

    The overlap ensures context doesn't get cut at segment boundaries.
    """
    segments: list[list[int]] = []
    overlap = max_len // 4  # ~25% overlap
    stride = max_len - overlap
    start = 0
    while start < len(tokens):
        end = min(start + max_len, len(tokens))
        segments.append(tokens[start:end])
        if end >= len(tokens):
            break
        start += stride
    return segments
