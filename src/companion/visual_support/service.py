from __future__ import annotations

import hashlib
import html
import logging
import math
import random
import time
from pathlib import Path

from companion.config import settings
from companion.images.cloudflare_flux import CloudflareFluxProvider
from companion.visual_support.prompt_builder import build_visual_prompt, infer_frame_count
from companion.visual_support.scene_planner import ScenePlanner
from companion.visual_support.schemas import VisualSupportRequest, VisualSupportResponse

logger = logging.getLogger(__name__)

# Flux runs a safety classifier on the OUTPUT.  For a fixed prompt+seed it
# deterministically produces the same (flagged) image, so a plain retry is
# pointless — we must vary the seed to get a different image.
_FLAG_MARKERS = ("3030", "flagged", "flag")
_MAX_REAL_ATTEMPTS = 3


def _is_content_flag(message: str) -> bool:
    low = message.lower()
    return "cloudflare 400" in low and any(m in low for m in _FLAG_MARKERS)


def safe_model_name(model: str) -> str:
    return (
        model.replace("@", "")
        .replace("/", "_")
        .replace(":", "_")
        .replace(".", "-")
    )


def extension_from_mime(mime_type: str) -> str:
    if mime_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if mime_type == "image/webp":
        return ".webp"
    if mime_type == "image/svg+xml":
        return ".svg"
    return ".png"


def tiles(width: int, height: int) -> int:
    return math.ceil(width / 512) * math.ceil(height / 512)


def estimate_cost_usd(model: str, width: int, height: int) -> float | None:
    tile_count = tiles(width, height)

    if "phoenix-1.0" in model:
        return (tile_count * 0.0058) + (25 * 0.00011)

    if "flux-2-klein-9b" in model:
        mp = (width * height) / 1_048_576
        if mp <= 1:
            return 0.015
        return 0.015 + ((mp - 1) * 0.002)

    if "flux-2-klein-4b" in model:
        return tile_count * 0.000287

    if "flux-2-dev" in model:
        return tile_count * 25 * 0.00041

    return None


class VisualSupportService:
    def __init__(
        self,
        output_dir: str | None = None,
        planner: ScenePlanner | None = None,
    ) -> None:
        configured_output_dir = getattr(settings, "visual_output_dir", "./generated_visuals")
        self.output_dir = Path(output_dir or configured_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._planner = planner

    def _get_planner(self) -> ScenePlanner:
        if self._planner is None:
            from companion.providers.factory import get_visual_planner_llm

            self._planner = ScenePlanner(get_visual_planner_llm())
        return self._planner

    def prepare(self, request: VisualSupportRequest) -> VisualSupportRequest:
        """Destila el extracto en escenas (8B) ANTES de armar el prompt de imagen.

        Sin esto, el generador recibía la prosa cruda y se le pedía elegir los
        momentos importantes: alucinaba y renderizaba texto.  Si el caller ya
        mandó `visual_events`, se respetan tal cual.  Si el planner falla, se
        sigue sin plan: la imagen se genera igual, nunca se rompe la petición."""
        if request.visual_events:
            return request

        frame_count = infer_frame_count(request.scope, request.text)
        try:
            plan = self._get_planner().plan(
                text=request.text,
                scope=request.scope,
                frame_count=frame_count,
                title=request.title,
            )
        except Exception as exc:  # noqa: BLE001 — degradar, no romper
            logger.warning("scene_planner falló, genero sin plan de escenas: %s", exc)
            return request

        update: dict[str, object] = {"visual_events": plan.visual_events}
        if plan.characters and not request.characters:
            update["characters"] = plan.characters
        return request.model_copy(update=update)

    def generate(self, request: VisualSupportRequest) -> VisualSupportResponse:
        request = self.prepare(request)
        model = request.model or settings.cloudflare_image_model
        prompt, frame_count = build_visual_prompt(request)

        # Per-request value wins; None falls back to the global default flag.
        default_mock = bool(getattr(settings, "visual_mock_enabled", False))
        use_mock = request.mock if request.mock is not None else default_mock

        cache_key = self._build_cache_key(
            prompt=prompt,
            model=model,
            width=request.width,
            height=request.height,
            seed=request.seed,
            mode="mock" if use_mock else "real",
        )

        cached_path = self._find_cached_image(cache_key)
        if cached_path:
            return self._response_from_cached_file(
                request=request,
                model=model,
                frame_count=frame_count,
                prompt=prompt,
                image_path=cached_path,
                mock=use_mock,
            )

        if use_mock:
            start = time.time()
            image_path = self._create_mock_svg(
                cache_key=cache_key,
                width=request.width,
                height=request.height,
                frame_count=frame_count,
                scope=request.scope,
            )
            elapsed = time.time() - start

            return VisualSupportResponse(
                image_url=f"/generated-visuals/{image_path.name}",
                image_path=str(image_path),
                provider="mock",
                model=model,
                scope=request.scope,
                frame_count=frame_count,
                width=request.width,
                height=request.height,
                elapsed_seconds=round(elapsed, 3),
                estimated_cost_usd=0.0,
                cached=False,
                mock=True,
                prompt_used=prompt,
            )

        start = time.time()
        provider = CloudflareFluxProvider(model=model)

        result = self._generate_with_flag_retry(
            provider=provider,
            prompt=prompt,
            width=request.width,
            height=request.height,
            seed=request.seed,
        )

        elapsed = time.time() - start

        ext = extension_from_mime(result.mime_type)
        image_path = self.output_dir / f"visual_{cache_key}{ext}"
        result.save(image_path)

        return VisualSupportResponse(
            image_url=f"/generated-visuals/{image_path.name}",
            image_path=str(image_path),
            provider=result.provider,
            model=result.model,
            scope=request.scope,
            frame_count=frame_count,
            width=request.width,
            height=request.height,
            elapsed_seconds=round(elapsed, 3),
            estimated_cost_usd=estimate_cost_usd(model, request.width, request.height),
            cached=False,
            mock=False,
            prompt_used=prompt,
        )

    def _generate_with_flag_retry(
        self,
        *,
        provider: CloudflareFluxProvider,
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
    ):
        """Call the provider, retrying with a fresh seed when Flux flags the
        output.  Same prompt+seed → same flagged image, so each retry uses a new
        random seed to get a different image.  Non-flag errors propagate at once."""
        current_seed = seed
        last_exc: Exception | None = None

        for attempt in range(_MAX_REAL_ATTEMPTS):
            try:
                return provider.generate(
                    prompt, width=width, height=height, seed=current_seed
                )
            except RuntimeError as exc:
                last_exc = exc
                if not _is_content_flag(str(exc)) or attempt == _MAX_REAL_ATTEMPTS - 1:
                    break
                current_seed = random.randint(1, 2_000_000_000)  # vary the image

        assert last_exc is not None
        if _is_content_flag(str(last_exc)):
            raise RuntimeError(
                "Cloudflare marcó la imagen como no apta tras "
                f"{_MAX_REAL_ATTEMPTS} intentos (content flag). Prueba con otro "
                "fragmento o ajusta el prompt."
            ) from last_exc
        raise last_exc

    def _build_cache_key(
        self,
        *,
        prompt: str,
        model: str,
        width: int,
        height: int,
        seed: int | None,
        mode: str,
    ) -> str:
        raw = "|".join(
            [
                mode,
                model,
                str(width),
                str(height),
                str(seed),
                prompt,
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _find_cached_image(self, cache_key: str) -> Path | None:
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
            path = self.output_dir / f"visual_{cache_key}{ext}"
            if path.exists():
                return path
        return None

    def _response_from_cached_file(
        self,
        *,
        request: VisualSupportRequest,
        model: str,
        frame_count: int,
        prompt: str,
        image_path: Path,
        mock: bool,
    ) -> VisualSupportResponse:
        return VisualSupportResponse(
            image_url=f"/generated-visuals/{image_path.name}",
            image_path=str(image_path),
            provider="mock" if mock else "cloudflare",
            model=model,
            scope=request.scope,
            frame_count=frame_count,
            width=request.width,
            height=request.height,
            elapsed_seconds=0.0,
            estimated_cost_usd=0.0 if mock else estimate_cost_usd(model, request.width, request.height),
            cached=True,
            mock=mock,
            prompt_used=prompt,
        )

    def _create_mock_svg(
        self,
        *,
        cache_key: str,
        width: int,
        height: int,
        frame_count: int,
        scope: str,
    ) -> Path:
        filename = f"visual_{cache_key}.svg"
        path = self.output_dir / filename

        svg = self._build_mock_svg(
            width=width,
            height=height,
            frame_count=frame_count,
            scope=scope,
        )

        path.write_text(svg, encoding="utf-8")
        return path

    def _build_mock_svg(
        self,
        *,
        width: int,
        height: int,
        frame_count: int,
        scope: str,
    ) -> str:
        safe_scope = html.escape(scope)

        margin = 36
        gap = 24

        if frame_count == 1:
            panel_width = width - (margin * 2)
            panel_height = height - (margin * 2)
            panels = [
                self._svg_panel(
                    x=margin,
                    y=margin,
                    w=panel_width,
                    h=panel_height,
                    index=0,
                )
            ]
        else:
            panel_width = (width - (margin * 2) - (gap * 2)) / 3
            panel_height = height - (margin * 2)
            panels = []
            for i in range(3):
                x = margin + i * (panel_width + gap)
                panels.append(
                    self._svg_panel(
                        x=x,
                        y=margin,
                        w=panel_width,
                        h=panel_height,
                        index=i,
                    )
                )

        panels_svg = "\n".join(panels)

        # Este mock no busca ser la imagen final; solo permite probar que el frontend
        # recibe y muestra una imagen sin consumir Cloudflare.
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#f7efe2"/>
  {panels_svg}
  <metadata>mock visual support - {safe_scope}</metadata>
</svg>
"""

    def _svg_panel(
        self,
        *,
        x: float,
        y: float,
        w: float,
        h: float,
        index: int,
    ) -> str:
        # Dibujos simples sin texto: marco, estantes, mesa, personaje y luz.
        shelf_y = y + h * 0.18
        desk_y = y + h * 0.66
        person_x = x + w * (0.32 if index != 2 else 0.48)
        person_y = y + h * 0.58

        glow_x = x + w * (0.72 if index != 1 else 0.55)
        glow_y = y + h * 0.38

        return f"""
  <g>
    <rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="18" fill="#fff7e8" stroke="#3b2d22" stroke-width="6"/>
    <circle cx="{glow_x:.1f}" cy="{glow_y:.1f}" r="{min(w, h) * 0.18:.1f}" fill="#ffd76a" opacity="0.28"/>

    <rect x="{x + w * 0.08:.1f}" y="{shelf_y:.1f}" width="{w * 0.84:.1f}" height="{h * 0.09:.1f}" rx="8" fill="#8a5a3c" opacity="0.75"/>
    <rect x="{x + w * 0.10:.1f}" y="{shelf_y + h * 0.12:.1f}" width="{w * 0.80:.1f}" height="{h * 0.08:.1f}" rx="8" fill="#8a5a3c" opacity="0.65"/>
    <rect x="{x + w * 0.12:.1f}" y="{shelf_y + h * 0.23:.1f}" width="{w * 0.76:.1f}" height="{h * 0.08:.1f}" rx="8" fill="#8a5a3c" opacity="0.55"/>

    <rect x="{x + w * 0.25:.1f}" y="{desk_y:.1f}" width="{w * 0.50:.1f}" height="{h * 0.08:.1f}" rx="10" fill="#c99a64"/>
    <rect x="{x + w * 0.34:.1f}" y="{desk_y - h * 0.06:.1f}" width="{w * 0.32:.1f}" height="{h * 0.04:.1f}" rx="6" fill="#fffdf4" stroke="#d3c2a2" stroke-width="3"/>

    <circle cx="{person_x:.1f}" cy="{person_y:.1f}" r="{min(w, h) * 0.055:.1f}" fill="#c58d62"/>
    <path d="M {person_x - w * 0.07:.1f} {person_y + h * 0.02:.1f} Q {person_x:.1f} {person_y - h * 0.13:.1f} {person_x + w * 0.07:.1f} {person_y + h * 0.02:.1f}" fill="#3b2720"/>
    <rect x="{person_x - w * 0.055:.1f}" y="{person_y + h * 0.06:.1f}" width="{w * 0.11:.1f}" height="{h * 0.16:.1f}" rx="16" fill="#efe0c8"/>
    <rect x="{person_x - w * 0.055:.1f}" y="{person_y + h * 0.20:.1f}" width="{w * 0.11:.1f}" height="{h * 0.10:.1f}" rx="10" fill="#7f2d3a"/>
  </g>
"""