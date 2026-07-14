"""
prompt_builder.py — El prompt que se le manda a Flux.

REGLA ÚNICA: el prompt NUNCA contiene el texto de la obra.  Solo escenas ya
destiladas por el 8B (scene_planner.py), en inglés.  Sin escenas no hay imagen.

Por qué es una regla y no una preferencia (2026-07-13, con la prueba delante):
durante días las imágenes salían con texto en español deformado dentro y se culpó
al modelo de "alucinar".  No alucinaba.  El planificador estaba caído — pedía un
modelo de OpenAI a NVIDIA y daba 404 en cada llamada —, el servicio se tragaba la
excepción, `visual_events` quedaba vacío y este builder caía a un fallback que
volcaba `request.text[:200]`: la prosa de Kafka, en español, como prompt.  Flux la
renderizaba de pie de foto, que es lo correcto: es lo que le habíamos pedido.  Se
confirmó hasheando el prompt reconstruido contra el nombre del PNG (el fichero se
llama sha256(prompt)).  Ese fallback ya no existe: sin plan, `build_visual_prompt`
levanta ValueError y el job falla con un error honesto.

Es un PIE DE FOTO, no una instrucción: un difusor no obedece órdenes, casa texto
con distribuciones de imágenes.  De ahí que no haya "Create…", "Goal:" ni muro de
prohibiciones, y que el anti-texto se pida en positivo ("wordless") en vez de
nombrar carteles y bocadillos.  Ojo: esto es higiene, no la cura — la cura fue
arreglar el planificador.  `negative_prompt` no es opción: flux-2-klein-9b va por
multipart en Workers AI y ese endpoint no lo acepta (images/cloudflare_flux.py).
"""
from __future__ import annotations

from companion.visual_support.schemas import VisualSupportRequest

_STYLE = (
    "children's storybook illustration, warm soft lighting, clean digital painting, "
    "gentle expressive faces, simple uncluttered background"
)
_PANEL_LABELS = ("Left panel", "Center panel", "Right panel")


def infer_frame_count(scope: str, text: str) -> int:
    """paragraph → 1 imagen; section / full_text → 3 viñetas."""
    if scope == "paragraph":
        return 1
    return 3


def _characters_clause(request: VisualSupportRequest) -> str:
    if not request.characters:
        return ""
    traits = "; ".join(f"{c.name}: {c.description}" for c in request.characters)
    return f" {traits}."


def _wordless_clause(allow_text: bool) -> str:
    # "wordless" en positivo: pide lo que SÍ queremos (una imagen sin letras) sin
    # nombrar carteles, títulos ni bocadillos, que es lo que los invocaba.
    return "" if allow_text else ", wordless"


def build_single_scene_prompt(request: VisualSupportRequest) -> str:
    scene = request.visual_events[0]
    return (
        f"{scene}"
        f"{_characters_clause(request)} "
        f"{_STYLE}{_wordless_clause(request.allow_text_in_image)}."
    )


def build_three_frame_prompt(request: VisualSupportRequest) -> str:
    events = request.visual_events[:3]
    panels = " ".join(f"{_PANEL_LABELS[i]}: {event}" for i, event in enumerate(events))
    return (
        "Triptych: three framed panels side by side, separated by thin dark borders. "
        f"{panels}"
        f"{_characters_clause(request)} "
        f"{_STYLE}, consistent character design across the three panels"
        f"{_wordless_clause(request.allow_text_in_image)}."
    )


def build_visual_prompt(request: VisualSupportRequest) -> tuple[str, int]:
    # Sin escenas no se dibuja.  El prompt NUNCA puede contener el texto de la
    # obra: Flux no lo "entiende", lo RENDERIZA — le das prosa en español y te
    # devuelve una página de cuento con esa prosa de pie de foto, en un español
    # deformado.  Eso era exactamente el bug que perseguíamos.
    if not request.visual_events:
        raise ValueError("no hay visual_events: no se puede construir el prompt")

    frame_count = infer_frame_count(request.scope, request.text)
    if frame_count == 1:
        return build_single_scene_prompt(request), frame_count
    return build_three_frame_prompt(request), frame_count
