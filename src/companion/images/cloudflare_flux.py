from __future__ import annotations

import base64
import math
from typing import Any

import httpx

from companion.config import settings
from companion.images.base import GeneratedImage, ImageProvider


class CloudflareFluxProvider(ImageProvider):
    """
    Cloudflare image provider.

    Soporta tres estilos de API:

    1. Modelos @cf clásicos:
       POST /accounts/{account_id}/ai/run/{model}
       Body JSON: {"prompt": "...", "width": ..., "height": ...}

    2. Modelos @cf FLUX.2 Klein:
       POST /accounts/{account_id}/ai/run/{model}
       Body multipart/form-data: prompt, width, height, steps

    3. Modelos nuevos del catálogo:
       POST /accounts/{account_id}/ai/run
       Body JSON:
       {
         "model": "krea/krea-2-medium",
         "input": {
           "prompt": "...",
           "aspect_ratio": "1:1",
           "resolution": "1K"
         }
       }
    """

    def __init__(
        self,
        model: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        if not settings.cloudflare_api_token:
            raise ValueError("CLOUDFLARE_API_TOKEN no configurado")
        if not settings.cloudflare_account_id:
            raise ValueError("CLOUDFLARE_ACCOUNT_ID no configurado")

        self.model = model or settings.cloudflare_image_model
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
        negative_prompt: str | None = None,
        seed: int | None = None,
    ) -> GeneratedImage:
        headers = {
            "Authorization": f"Bearer {settings.cloudflare_api_token}",
        }

        if self._uses_catalog_run_endpoint():
            url = (
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{settings.cloudflare_account_id}/ai/run"
            )
            resp = self._post_catalog_json(
                url=url,
                headers={**headers, "Content-Type": "application/json"},
                prompt=prompt,
                width=width,
                height=height,
                seed=seed,
            )

        elif self._requires_multipart():
            url = (
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{settings.cloudflare_account_id}/ai/run/{self.model}"
            )
            resp = self._post_multipart(
                url=url,
                headers=headers,
                prompt=prompt,
                width=width,
                height=height,
            )

        else:
            url = (
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{settings.cloudflare_account_id}/ai/run/{self.model}"
            )
            resp = self._post_direct_json(
                url=url,
                headers={**headers, "Content-Type": "application/json"},
                prompt=prompt,
                width=width,
                height=height,
                negative_prompt=negative_prompt,
                seed=seed,
            )

        if resp.status_code >= 400:
            raise RuntimeError(
                f"Error Cloudflare {resp.status_code}: {resp.text}"
            )

        return self._parse_response(
            resp=resp,
            prompt=prompt,
            width=width,
            height=height,
        )

    def _uses_catalog_run_endpoint(self) -> bool:
        """
        Modelos sin prefijo @cf usan el endpoint genérico /ai/run
        con body {"model": "...", "input": {...}}.
        """
        return not self.model.startswith("@cf/")

    def _requires_multipart(self) -> bool:
        """
        FLUX.2 Klein en Workers AI requiere multipart/form-data.
        """
        return any(
            key in self.model
            for key in (
                "flux-2-klein-4b",
                "flux-2-klein-9b",
                "flux-2-dev",
            )
        )

    def _post_direct_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        prompt: str,
        width: int,
        height: int,
        negative_prompt: str | None,
        seed: int | None,
    ) -> httpx.Response:
        payload: dict[str, Any] = {
            "prompt": prompt,
            "width": width,
            "height": height,
        }

        if seed is not None:
            payload["seed"] = seed

        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        # Ajustes útiles para Leonardo Phoenix / Lucid.
        if "leonardo" in self.model:
            payload["guidance"] = 4
            payload["num_steps"] = 25

        with httpx.Client(timeout=self.timeout) as client:
            return client.post(url, headers=headers, json=payload)

    def _post_multipart(
        self,
        *,
        url: str,
        headers: dict[str, str],
        prompt: str,
        width: int,
        height: int,
    ) -> httpx.Response:
        """
        httpx solo envía multipart/form-data si usamos files.
        Cada campo textual se manda como (None, valor).
        """
        files = {
            "prompt": (None, prompt),
            "width": (None, str(width)),
            "height": (None, str(height)),
            "steps": (None, "25"),
        }

        with httpx.Client(timeout=self.timeout) as client:
            return client.post(url, headers=headers, files=files)

    def _post_catalog_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
    ) -> httpx.Response:
        payload = {
            "model": self.model,
            "input": self._build_catalog_input(
                prompt=prompt,
                width=width,
                height=height,
                seed=seed,
            ),
        }

        with httpx.Client(timeout=self.timeout) as client:
            return client.post(url, headers=headers, json=payload)

    def _build_catalog_input(
        self,
        *,
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
    ) -> dict[str, Any]:
        aspect_ratio = self._aspect_ratio_from_size(width, height)

        if self.model.startswith("krea/"):
            data: dict[str, Any] = {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "resolution": "1K",
                # raw reduce expansión creativa; mejor para pruebas educativas controladas.
                "creativity": "raw",
                "intensity": 0,
                "complexity": 0,
                "movement": 0,
            }

            if seed is not None:
                data["seed"] = seed

            return data

        if self.model.startswith("google/nano-banana"):
            data = {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "resolution": "1K",
                "output_format": "png",
            }

            # La documentación que pasaste no lista seed para nano-banana-2-lite.
            # No lo enviamos para evitar errores por additionalProperties=false.
            return data

        # Fallback para otros modelos de catálogo.
        return {
            "prompt": prompt,
        }

    def _aspect_ratio_from_size(self, width: int, height: int) -> str:
        """
        Convierte width/height a una relación soportada por Krea/Nano Banana.
        Para esta prueba usaremos 1024x1024, así que será 1:1.
        """
        ratio = width / height

        candidates = {
            "1:1": 1.0,
            "4:3": 4 / 3,
            "3:2": 3 / 2,
            "16:9": 16 / 9,
            "2.35:1": 2.35,
            "4:5": 4 / 5,
            "2:3": 2 / 3,
            "9:16": 9 / 16,
        }

        # Nano Banana soporta también 21:9, pero 2.35:1 es suficientemente cercano
        # y Krea lo soporta. Para pruebas generales usamos el conjunto común.
        return min(candidates, key=lambda key: abs(candidates[key] - ratio))

    def _parse_response(
        self,
        *,
        resp: httpx.Response,
        prompt: str,
        width: int,
        height: int,
    ) -> GeneratedImage:
        ctype = resp.headers.get("content-type", "")

        # Algunos modelos @cf devuelven imagen binaria directamente.
        if ctype.startswith("image/"):
            return GeneratedImage(
                provider="cloudflare",
                model=self.model,
                prompt=prompt,
                width=width,
                height=height,
                mime_type=ctype.split(";")[0],
                image_bytes=resp.content,
            )

        body = resp.json()
        result = body.get("result", body)

        image_value = self._extract_image_value(result)

        if not image_value:
            raise RuntimeError(f"Respuesta Cloudflare inesperada: {body}")

        image_bytes, mime_type = self._image_value_to_bytes(image_value)

        return GeneratedImage(
            provider="cloudflare",
            model=self.model,
            prompt=prompt,
            width=width,
            height=height,
            mime_type=mime_type,
            image_bytes=image_bytes,
        )

    def _extract_image_value(self, result: Any) -> str | None:
        if isinstance(result, str):
            return result

        if not isinstance(result, dict):
            return None

        for key in ("image", "base64", "b64_json", "url"):
            if isinstance(result.get(key), str):
                return result[key]

        images = result.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                for key in ("image", "base64", "b64_json", "url"):
                    if isinstance(first.get(key), str):
                        return first[key]

        data = result.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                for key in ("image", "base64", "b64_json", "url"):
                    if isinstance(first.get(key), str):
                        return first[key]

        return None

    def _image_value_to_bytes(self, image_value: str) -> tuple[bytes, str]:
        """
        Cloudflare puede devolver:
        - URL presignada
        - base64
        - data URL
        """
        if image_value.startswith("http://") or image_value.startswith("https://"):
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(image_value)
                r.raise_for_status()
                mime_type = r.headers.get("content-type", "image/png").split(";")[0]
                return r.content, mime_type

        if image_value.startswith("data:image"):
            header, image_b64 = image_value.split(",", 1)
            mime_type = header.split(";")[0].replace("data:", "")
            return base64.b64decode(image_b64), mime_type

        # Asumimos base64 plano.
        return base64.b64decode(image_value), "image/png"