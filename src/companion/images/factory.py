from __future__ import annotations

from companion.images.cloudflare_flux import CloudflareFluxProvider
from companion.images.nvidia_image import NvidiaImageProvider


def get_image_provider(name: str):
    key = name.lower()

    if key in {"cloudflare", "cloudflare_flux", "flux"}:
        return CloudflareFluxProvider()

    if key in {"nvidia", "nvidia_nim"}:
        return NvidiaImageProvider()

    raise ValueError(f"Proveedor de imagen no soportado: {name}")