from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from companion.config import settings
from companion.visual_support.prompt_builder import build_visual_prompt
from companion.visual_support.schemas import VisualSupportRequest, VisualSupportResponse
from companion.visual_support.service import VisualSupportService


visual_output_dir = Path(settings.visual_output_dir)
visual_output_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Reading Companion API",
    version="0.1.0",
)

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


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Reading Companion API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/visual-support/preview")
def preview_visual_support_prompt(payload: VisualSupportRequest) -> dict[str, object]:
    """
    Endpoint de prueba que NO consume Cloudflare.
    Sirve para validar el JSON y ver el prompt generado.
    """
    prompt, frame_count = build_visual_prompt(payload)

    return {
        "status": "ok",
        "scope": payload.scope,
        "frame_count": frame_count,
        "model": payload.model or settings.cloudflare_image_model,
        "width": payload.width,
        "height": payload.height,
        "prompt": prompt,
    }


@app.post("/api/visual-support", response_model=VisualSupportResponse)
def generate_visual_support(
    payload: VisualSupportRequest,
    request: Request,
) -> VisualSupportResponse:
    try:
        service = VisualSupportService()
        response = service.generate(payload)

        base_url = str(request.base_url).rstrip("/")
        response.image_url = f"{base_url}{response.image_url}"

        return response

    except Exception as exc:
        message = str(exc)

        if (
            "used up your daily free allocation" in message
            or "daily free allocation" in message
            or "429" in message
            or "quota" in message.lower()
            or "neurons" in message.lower()
        ):
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "cloudflare_quota_exceeded",
                    "message": message,
                },
            ) from exc

        if "Error Cloudflare" in message or "Cloudflare" in message:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "cloudflare_generation_error",
                    "message": message,
                },
            ) from exc

        raise HTTPException(
            status_code=500,
            detail={
                "error": "visual_support_internal_error",
                "message": message,
            },
        ) from exc