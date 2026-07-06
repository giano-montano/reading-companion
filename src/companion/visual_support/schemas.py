from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


VisualScope = Literal["paragraph", "section", "full_text"]


class VisualCharacter(BaseModel):
    name: str = Field(..., description="Nombre del personaje")
    description: str = Field(..., description="Descripción visual breve")


class VisualSupportRequest(BaseModel):
    text: str = Field(..., min_length=20)
    scope: VisualScope = "section"

    title: str | None = None
    section_id: str | None = None

    visual_events: list[str] = Field(default_factory=list)
    characters: list[VisualCharacter] = Field(default_factory=list)

    model: str | None = None
    width: int = 1536
    height: int = 1024
    seed: int | None = 12345

    allow_text_in_image: bool = False

    # Para integración sin gastar Cloudflare
    mock: bool = False


class VisualSupportResponse(BaseModel):
    image_url: str
    image_path: str

    provider: str
    model: str

    scope: VisualScope
    frame_count: int

    width: int
    height: int

    elapsed_seconds: float
    estimated_cost_usd: float | None = None

    cached: bool = False
    mock: bool = False

    prompt_used: str