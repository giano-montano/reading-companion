from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from companion.api.books import router as books_router
from companion.api.visual import router as visual_router
from companion.config import settings

visual_output_dir = Path(settings.visual_output_dir)
visual_output_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Reading Companion API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/generated-visuals",
    StaticFiles(directory=visual_output_dir),
    name="generated_visuals",
)

app.include_router(books_router)
app.include_router(visual_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Reading Companion API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
