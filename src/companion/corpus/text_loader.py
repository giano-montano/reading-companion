from __future__ import annotations
from collections.abc import Iterator
from pathlib import Path

from companion.corpus.base import CorpusLoader
from companion.schemas import Document


class TextLoader(CorpusLoader):
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def load(self) -> Iterator[Document]:
        text = self._path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        yield Document(
            text=text,
            source_metadata={"source": self._path.name, "path": str(self._path)},
        )
