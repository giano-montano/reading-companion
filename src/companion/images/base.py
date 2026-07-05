from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GeneratedImage:
    provider: str
    model: str
    prompt: str
    width: int
    height: int
    mime_type: str
    image_bytes: bytes
    revised_prompt: str | None = None

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.image_bytes)
        return p


class ImageProvider(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
        negative_prompt: str | None = None,
        seed: int | None = None,
    ) -> GeneratedImage:
        raise NotImplementedError