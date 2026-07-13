"""
/api/images — scope-driven, asynchronous illustration generation.

Direct endpoints (no router): the frontend selects a scope and the backend
resolves it to chunk text via `ChunkCatalog`, then generates the image in the
background.  The client gets a `job_id` immediately and polls until ready.

    POST /api/images         → 202 {job_id, poll_url}
    GET  /api/images/{job_id} → {status, image_url?, error?}

Scope selectors (all reduce to chunks, then to grounding text):
    vista         lo que veo        → chunk_ids (visible focus)
    seccion       esta sección      → chunk_ids (the section's chunks)
    hasta_maximo  progreso máximo   → max_progress_chunk_index
    obra          toda la obra      → every chunk of book_id
"""
from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from companion.scope.catalog import build_scope_text, get_catalog
from companion.visual_support.schemas import VisualCharacter, VisualSupportRequest
from companion.images.jobs import create_job, get_job
from companion.images.runner import run_image_job

router = APIRouter(prefix="/api/images", tags=["images"])

MIN_TEXT_LEN = 20  # VisualSupportRequest.text minimum


class ImageScope(str, Enum):
    VISTA = "vista"
    SECCION = "seccion"
    HASTA_MAXIMO = "hasta_maximo"
    OBRA = "obra"


# Our scope → the visual prompt's frame semantics (paragraph=1 panel, else 3).
_SCOPE_TO_VISUAL: dict[ImageScope, str] = {
    ImageScope.VISTA: "paragraph",
    ImageScope.SECCION: "section",
    ImageScope.HASTA_MAXIMO: "full_text",
    ImageScope.OBRA: "full_text",
}


class ImageRequest(BaseModel):
    book_id: str
    scope: ImageScope

    # Selector inputs (only the ones relevant to `scope` are used):
    chunk_ids: list[str] = Field(default_factory=list)         # vista / seccion
    max_progress_chunk_index: int | None = None                # hasta_maximo

    # Visual passthrough (all optional, sensible defaults in VisualSupportRequest):
    title: str | None = None
    visual_events: list[str] = Field(default_factory=list)
    characters: list[VisualCharacter] = Field(default_factory=list)
    model: str | None = None
    width: int = 1536
    height: int = 1024
    seed: int | None = 12345
    allow_text_in_image: bool = False
    # None → global default (settings.visual_mock_enabled); True/False → force.
    mock: bool | None = None


class ImageJobCreated(BaseModel):
    job_id: str
    poll_url: str
    status: str = "pending"


class ImageJobStatus(BaseModel):
    job_id: str
    status: str
    image_url: str | None = None
    error: str | None = None
    meta: dict = Field(default_factory=dict)


def _resolve_text(payload: ImageRequest) -> str:
    catalog = get_catalog(payload.book_id)

    if payload.scope in (ImageScope.VISTA, ImageScope.SECCION):
        if not payload.chunk_ids:
            raise HTTPException(
                status_code=422,
                detail=f"scope '{payload.scope.value}' requires chunk_ids",
            )
        chunks = catalog.by_ids(payload.chunk_ids)
    elif payload.scope is ImageScope.HASTA_MAXIMO:
        if payload.max_progress_chunk_index is None:
            raise HTTPException(
                status_code=422,
                detail="scope 'hasta_maximo' requires max_progress_chunk_index",
            )
        chunks = catalog.up_to_index(payload.max_progress_chunk_index)
    else:  # OBRA
        chunks = catalog.all()

    return build_scope_text(chunks)


@router.post("", response_model=ImageJobCreated, status_code=202)
def create_image(
    payload: ImageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ImageJobCreated:
    try:
        text = _resolve_text(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if len(text.strip()) < MIN_TEXT_LEN:
        raise HTTPException(
            status_code=422,
            detail="Selected scope resolved to too little text to illustrate.",
        )

    vsr = VisualSupportRequest(
        text=text,
        scope=_SCOPE_TO_VISUAL[payload.scope],  # type: ignore[arg-type]
        title=payload.title,
        visual_events=payload.visual_events,
        characters=payload.characters,
        model=payload.model,
        width=payload.width,
        height=payload.height,
        seed=payload.seed,
        allow_text_in_image=False, #payload.allow_text_in_image,
        mock=payload.mock,
    )

    job = create_job()
    background_tasks.add_task(run_image_job, job.job_id, vsr)

    base_url = str(request.base_url).rstrip("/")
    return ImageJobCreated(
        job_id=job.job_id,
        poll_url=f"{base_url}/api/images/{job.job_id}",
    )


@router.get("/{job_id}", response_model=ImageJobStatus)
def get_image(job_id: str, request: Request) -> ImageJobStatus:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'")

    image_url = job.image_url
    if image_url and image_url.startswith("/"):
        image_url = f"{str(request.base_url).rstrip('/')}{image_url}"

    return ImageJobStatus(
        job_id=job.job_id,
        status=job.status,
        image_url=image_url,
        error=job.error,
        meta=job.meta,
    )
