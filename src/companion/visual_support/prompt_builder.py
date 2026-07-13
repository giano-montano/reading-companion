from __future__ import annotations

import re

from companion.visual_support.schemas import VisualSupportRequest

# El extracto crudo YA NO se vuelca entero en el prompt: un modelo de difusión no
# hace comprensión lectora, y una pared de prosa lo llevaba a alucinar y a
# renderizar texto dentro de la imagen.  Las escenas las destila antes el 8B
# (visual_support/scene_planner.py); aquí solo queda un extracto breve como
# anclaje de tono.
_BRIEF_EXCERPT_CHARS = 400


def _brief_excerpt(text: str, max_chars: int = _BRIEF_EXCERPT_CHARS) -> str:
    """Primeras frases del extracto, cortando en límite de frase."""
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_chars:
        return clean

    window = clean[:max_chars]
    cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
    if cut > max_chars // 2:
        return window[: cut + 1]
    return window.rsplit(" ", 1)[0] + "…"


def build_grounding_block(text: str) -> str:
    return f"""
Source excerpt (for tone and setting only — do NOT draw or render any of these words):
\"\"\"
{_brief_excerpt(text)}
\"\"\"
""".strip()


def infer_frame_count(scope: str, text: str) -> int:
    """
    Regla MVP:
    - paragraph: 1 imagen única
    - section: 3 paneles
    - full_text: 3 paneles resumen global
    """
    if scope == "paragraph":
        return 1

    return 3


def build_visual_prompt(request: VisualSupportRequest) -> tuple[str, int]:
    frame_count = infer_frame_count(request.scope, request.text)

    if frame_count == 1:
        return build_single_scene_prompt(request), frame_count

    return build_three_frame_prompt(request), frame_count


def build_character_block(request: VisualSupportRequest) -> str:
    if not request.characters:
        return """
Character consistency:
- Keep the same main characters visually consistent if they appear more than once.
- Do not add extra characters unless the text clearly requires them.
""".strip()

    lines = ["Character consistency:"]
    for character in request.characters:
        lines.append(f"- {character.name}: {character.description}")

    lines.append("- Do not add extra characters unless the text clearly requires them.")
    return "\n".join(lines)


def build_event_block(request: VisualSupportRequest, frame_count: int) -> str:
    if request.visual_events:
        selected_events = request.visual_events[:frame_count]
        lines = [
            f"Use these exact {len(selected_events)} visual moments in chronological order:"
        ]

        labels = ["Left framed scene", "Center framed scene", "Right framed scene"]

        for index, event in enumerate(selected_events):
            if frame_count == 1:
                lines.append(f"- Main scene: {event}")
            else:
                label = labels[index] if index < len(labels) else f"Scene {index + 1}"
                lines.append(f"- {label}: {event}")

        return "\n".join(lines)

    if frame_count == 1:
        return """
Choose one visually important moment from the source text.
The image should help the student understand the selected paragraph or fragment.
""".strip()

    return """
Choose exactly three visually important moments from the source text.
The three moments must be chronological and must summarize the beginning, middle, and end of the selected text.
Do not include events that are not present in the source text.
""".strip()


def build_single_scene_prompt(request: VisualSupportRequest) -> str:
    character_block = build_character_block(request)
    event_block = build_event_block(request, frame_count=1)

    title_line = f"Title or context: {request.title}" if request.title else ""

    anti_text_rules = build_anti_text_rules(request.allow_text_in_image)

    return f"""
Create one educational storybook illustration for secondary-school reading support.

Goal:
Create a clear visual support image that helps a student understand the selected text.

{title_line}

Visual style:
- clean digital storybook illustration
- warm, soft lighting
- visually appealing for students
- calm and educational
- expressive but not exaggerated
- easy to understand at a glance
- suitable for viewing in a side chat panel

{character_block}

Visual moment:
{event_block}

{build_grounding_block(request.text)}

{anti_text_rules}

Final check before generating:
The output must be one clear illustration with no unnecessary elements and no spoilers beyond the source text.
""".strip()


def build_three_frame_prompt(request: VisualSupportRequest) -> str:
    character_block = build_character_block(request)
    event_block = build_event_block(request, frame_count=3)

    title_line = f"Title or context: {request.title}" if request.title else ""

    anti_text_rules = build_anti_text_rules(request.allow_text_in_image)

    scope_instruction = ""
    if request.scope == "full_text":
        scope_instruction = """
Because the selected scope is a full text or complete work, summarize only the three most important visual stages:
1. beginning
2. central conflict or discovery
3. final state or most important outcome
Do not try to include every event.
""".strip()

    return f"""
Create ONE single wide educational illustration divided into EXACTLY THREE separate framed visual scenes.

Very important layout rules:
- The final image must have exactly three separate rectangular frames.
- The three frames must be arranged horizontally from left to right.
- The left frame, center frame, and right frame must be clearly separated by simple dark borders.
- Do not create one continuous scene.
- Do not merge the three moments into one room.
- Do not place multiple copies of the same character inside the same frame.
- Each frame must show only one moment from the story.
- The image must be understandable even when viewed inside a small side chat panel.

This is NOT:
- a comic strip with captions
- a manga page
- a page with text
- an infographic
- a poster
- a worksheet

Goal:
Visually summarize the selected text in a clear, educational, easy-to-understand way for secondary-school reading support.

{title_line}

{scope_instruction}

Visual style:
- clean digital storybook illustration
- warm, soft lighting
- visually appealing for students
- calm and educational
- expressive but not exaggerated
- easy to understand at a glance
- consistent character design across all three frames

{character_block}

Three framed visual scenes:
{event_block}

{build_grounding_block(request.text)}

{anti_text_rules}

Final check before generating:
The output must be one image with exactly three framed illustrations and no spoilers beyond the source text.
""".strip()


def build_anti_text_rules(allow_text: bool) -> str:
    if allow_text:
        return """
Text rules:
- Avoid text unless absolutely necessary.
- If text appears, it must be minimal, large, clean, and clearly readable.
- Do not include fake letters or unreadable pseudo-text.
- Prefer visual storytelling instead of written explanations.
""".strip()

    return """
Strict anti-text rules:
- no text anywhere, no captions, no labels, no title, no headings, no written symbols, no fake letters, no readable text, no unreadable pseudo-text, no text boxes, no white caption areas, no speech bubbles, no thought bubbles, no diary writing, no book titles, no posters with text, no signs, only drawings inside the image
""".strip()