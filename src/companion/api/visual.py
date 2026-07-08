from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from companion.config import settings
from companion.visual_support.prompt_builder import build_visual_prompt
from companion.visual_support.schemas import VisualSupportRequest, VisualSupportResponse
from companion.visual_support.service import VisualSupportService

router = APIRouter(prefix="/api/visual-support", tags=["visual-support"])


@router.post("/preview")
def preview_visual_support_prompt(payload: VisualSupportRequest) -> dict[str, object]:
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


@router.post("", response_model=VisualSupportResponse)
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
        if any(k in message for k in (
            "daily free allocation", "429", "quota", "neurons",
        )):
            raise HTTPException(status_code=429, detail={
                "error": "cloudflare_quota_exceeded", "message": message,
            }) from exc
        if "Cloudflare" in message:
            raise HTTPException(status_code=502, detail={
                "error": "cloudflare_generation_error", "message": message,
            }) from exc
        raise HTTPException(status_code=500, detail={
            "error": "visual_support_internal_error", "message": message,
        }) from exc
