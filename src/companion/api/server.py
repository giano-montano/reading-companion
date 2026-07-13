from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from companion.api.books import router as books_router
from companion.api.chat import router as chat_router
from companion.api.images import router as images_router
from companion.api.visual import router as visual_router
from companion.config import settings

visual_output_dir = Path(settings.visual_output_dir)
visual_output_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Reading Companion API", version="0.1.0")

_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
app.include_router(chat_router)
app.include_router(images_router)
app.include_router(visual_router)


@app.on_event("startup")
def _warmup() -> None:
    """Build the heavy QA-RAG singletons (E5 embedder ~24s, Chroma, LLMs) at
    startup so the first /api/chat request isn't penalized. Best-effort: a
    failure here (e.g. missing NVIDIA key) must not block the read-only API."""
    try:
        from companion.api.deps import warmup
        warmup()
    except Exception as exc:  # noqa: BLE001 — warmup is optional
        import logging
        logging.getLogger(__name__).warning("Chat warmup skipped: %s", exc)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Reading Companion API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
