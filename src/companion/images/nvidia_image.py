from __future__ import annotations

import base64
from typing import Any

import httpx

from companion.config import settings
from companion.images.base import GeneratedImage, ImageProvider


class NvidiaImageProvider(ImageProvider):
    """
    NVIDIA Visual GenAI provider.

    Ojo:
    - Para chat/LLM usamos https://integrate.api.nvidia.com/v1
    - Para imágenes FLUX usamos https://ai.api.nvidia.com/v1/genai/...
    """

    def __init__(
        self,
        model: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        if not settings.nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY no configurada")

        self.model = model or settings.nvidia_image_model
        self.timeout = timeout

    def _endpoint_for_model(self) -> str:
        model = self.model.strip()

        if model == "flux.1-schnell":
            return "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell"

        if model == "flux.1-dev":
            return "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"

        if model == "flux.2-klein-4b":
            return "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b"

        raise ValueError(
            f"Modelo NVIDIA de imagen no soportado en este wrapper: {model}. "
            "Usa flux.1-schnell, flux.1-dev o flux.2-klein-4b."
        )

    def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
        negative_prompt: str | None = None,
        seed: int | None = None,
    ) -> GeneratedImage:
        url = self._endpoint_for_model()

        payload: dict[str, Any] = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "samples": 1,
            "steps": 1,
        }

        if seed is not None:
            payload["seed"] = seed

        # NVIDIA FLUX.1 Schnell no documenta negative_prompt como parámetro central.
        # Lo dejamos fuera para evitar 422 por validación.
        # Si luego prueban otro modelo que sí lo acepte, se puede agregar por modelo.

        headers = {
            "Authorization": f"Bearer {settings.nvidia_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        print(f"[NVIDIA] Calling {url}")
        print(f"[NVIDIA] Payload: width={width}, height={height}, steps={payload.get('steps')}, samples={payload.get('samples')}")

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)

            if resp.status_code >= 400:
                raise RuntimeError(
                    "Error NVIDIA Visual GenAI "
                    f"{resp.status_code}: {resp.text}"
                )

            body = resp.json()

        image_b64 = self._extract_base64_image(body)

        if not image_b64:
            raise RuntimeError(f"Respuesta NVIDIA inesperada: {body}")

        # A veces puede venir como data URL: data:image/png;base64,...
        if image_b64.startswith("data:image"):
            header, image_b64 = image_b64.split(",", 1)
            mime_type = header.split(";")[0].replace("data:", "")
        else:
            mime_type = "image/png"

        return GeneratedImage(
            provider="nvidia",
            model=self.model,
            prompt=prompt,
            width=width,
            height=height,
            mime_type=mime_type,
            image_bytes=base64.b64decode(image_b64),
        )

    def _extract_base64_image(self, body: dict[str, Any]) -> str | None:
        """
        NVIDIA puede cambiar ligeramente el formato entre modelos.
        Este extractor intenta cubrir los formatos más comunes.
        """

        # Caso directo
        if isinstance(body.get("image"), str):
            return body["image"]

        # Caso artifacts
        artifacts = body.get("artifacts")
        if isinstance(artifacts, list) and artifacts:
            first = artifacts[0]
            if isinstance(first, dict):
                for key in ("base64", "b64_json", "image"):
                    if isinstance(first.get(key), str):
                        return first[key]

        # Caso data[0].b64_json o data[0].image
        data = body.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                for key in ("b64_json", "image", "base64"):
                    if isinstance(first.get(key), str):
                        return first[key]

        # Caso images[0]
        images = body.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                for key in ("base64", "b64_json", "image"):
                    if isinstance(first.get(key), str):
                        return first[key]

        return None