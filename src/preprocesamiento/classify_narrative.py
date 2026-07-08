"""Classify is_narrative for all blocks in data/master/*.master.json files.

Applies rules to mark blocks as narrative (true) or non-narrative (false).
Generates corrected JSON files + a doubts file for manual review.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
MASTER_DIR = ROOT / "data" / "master"
DOUBTS = []


# ---------------------------------------------------------------------------
# Shared pattern helpers
# ---------------------------------------------------------------------------

def _text(block: dict) -> str:
    return block.get("text", "").strip()


def _type(block: dict) -> str:
    return block.get("type", "")


def _id(block: dict) -> str:
    return block.get("id_block", "")


def _is_elejandria_footer(text: str) -> bool:
    return any(k in text.lower() for k in [
        "gracias por leer este libro",
        "www.elejandria.com",
        "descubre nuestra colección",
        "dominio público en castellano en nuestra web",
    ])


def _is_epub_version(text: str) -> bool:
    return bool(re.match(r"^ePub\s*(v|r|base)", text, re.IGNORECASE))


def _is_editorial_credit(text: str) -> bool:
    return any(k in text.lower() for k in [
        "editor digital:",
        "titivillus",
        "epublibre",
        "www.epublibre",
    ])


def _is_toc_entry(text: str) -> bool:
    """Match TOC chapter entries like 'Capítulo 1', 'Capítulo I', etc."""
    return bool(re.match(
        r"^(Capítulo|Capitulo)\s+[IVXLCDM\d]+(\s*[–\-]\s*(Capítulo|Capitulo)\s+[IVXLCDM\d]+)*$",
        text, re.IGNORECASE
    ))


def _is_conclusion_toc(text: str) -> bool:
    return text.strip().lower() in ("conclusión", "conclusion", "epílogo", "epilogo")


def _is_copyright(text: str) -> bool:
    return any(k in text for k in ["©", "Copyright", "Todos los derechos"])


def _is_source_info(text: str) -> bool:
    return any(k in text.lower() for k in [
        "fuente:", "traductor:", "wikisource", "elejandría",
        "project gutenberg", "dominio público", "dmca",
    ])


def _is_legal_notice(text: str) -> bool:
    text_lower = text.lower()
    return any(k in text_lower for k in [
        "dmca@", "procederemos a su retirada", "derecho a reclamar",
        "se supone de dominio público",
    ])


def _is_publicado(text: str) -> bool:
    return bool(re.match(r"^Publicado:\s*", text))


def _is_author_bio(text: str, next_blocks: list[dict], idx: int, blocks: list[dict]) -> bool:
    """Check if we're in an author bio section at the end."""
    # Heuristic: after "FIN" or at the very end with biographical content
    keywords = ["nació en", "fue un escritor", "novelista", "premio nobel",
                "premio pulitzer", "periodista y", "narrador, poeta"]
    if any(k in text.lower() for k in keywords):
        # Check if nearby blocks are also biographical
        return True
    return False


# ---------------------------------------------------------------------------
# Per-book classification rules
# ---------------------------------------------------------------------------

def classify_cronica(blocks: list[dict]) -> list[dict]:
    book_id = "cronica_de_una_muerte_anunciada_gabriel_garcia_marquez"
    for i, b in enumerate(blocks):
        t = _text(b)
        _id_block = _id(b)

        # Front matter: synopsis, portada, editorial
        # block::1 = synopsis
        if i == 0:
            b["is_narrative"] = False  # Synopsis/back-cover
        # block::2 = "Gabriel García Márquez" (portada)
        elif i == 1 and t == "Gabriel García Márquez":
            b["is_narrative"] = False
        # block::3 = "Crónica de una muerte anunciada" (portada title)
        elif i == 2 and t == "Crónica de una muerte anunciada":
            b["is_narrative"] = False
        # block::4 = ePub version
        elif i == 3 and _is_epub_version(t):
            b["is_narrative"] = False
        # block::5 = converter name
        elif i == 4 and "Amadeuzzzz" in t:
            b["is_narrative"] = False
        # block::6-8 = epigraph by Gil Vicente (literary context)
        # These remain true
        # block::9 = "Prólogo" (starts preface)
        # block::10 = "Santiago Gamboa" (preface author)
        # blocks::11-14 = preface content → all true
        # block::15 "1" onwards → narrative → all true
        # block::306 "FIN" → narrative, true

        # Everything else stays as is (defaults to true for narrative)
    return blocks


def classify_mago_de_oz(blocks: list[dict]) -> list[dict]:
    # Blocks 1-2: portada (title + author) → false
    # Everything else: narrative
    for i, b in enumerate(blocks):
        t = _text(b)
        if i == 0 and t == "El maravilloso mago de Oz":
            b["is_narrative"] = False
        elif i == 1 and t == "Lyman Frank Baum":
            b["is_narrative"] = False
    return blocks


def classify_viejo_y_el_mar(blocks: list[dict]) -> list[dict]:
    for i, b in enumerate(blocks):
        t = _text(b)
        _id_block = _id(b)

        # Front matter editorial
        # block::1-2: synopsis
        if i in (0, 1) and ("El viejo y el mar" in t or "Un viejo lobo" in t):
            b["is_narrative"] = False
        # block::3: author name (portada)
        elif i == 2 and t == "Ernest Hemingway":
            b["is_narrative"] = False
        # block::4: title (portada)
        elif i == 3 and t == "El viejo y el mar":
            b["is_narrative"] = False
        # block::5: ePub version
        elif i == 4 and _is_epub_version(t):
            b["is_narrative"] = False
        # block::6: Titivillus
        elif i == 5 and "Titivillus" in t:
            b["is_narrative"] = False
        # block::7: original title
        elif i == 6 and "Título original:" in t:
            b["is_narrative"] = False
        # block::8: copyright
        elif i == 7 and "Ernest Hemingway, 1952" in t:
            b["is_narrative"] = False
        # block::9: cover image
        elif i == 8 and "Imagen de portada:" in t:
            b["is_narrative"] = False
        # block::10: editor digital
        elif i == 9 and _is_editorial_credit(t):
            b["is_narrative"] = False
        # block::11: ePub base
        elif i == 10 and _is_epub_version(t):
            b["is_narrative"] = False
        # block::12: dedication "A Charles Scribner y Max Perkins." → true (literary)
        # block::13 onwards: narrative → true
        # At the end:
        # block::671 "FIN" → true
        # block::672 author bio → false
        elif i == len(blocks) - 3:
            b["is_narrative"] = False  # Author bio
        # block::673 "Notas" → false (editorial note)
        elif i == len(blocks) - 2 and t == "Notas":
            b["is_narrative"] = False
            DOUBTS.append({
                "book_id": "el_viejo_y_el_mar_ernest_hemingway",
                "id_block": _id_block,
                "text": t,
                "reason": "Bloque 'Notas' con nota editorial - marcado false, revisar si es parte del libro"
            })
        # block::674 footnote → false
        elif i == len(blocks) - 1 and "[1]" in t:
            b["is_narrative"] = False
            DOUBTS.append({
                "book_id": "el_viejo_y_el_mar_ernest_hemingway",
                "id_block": _id_block,
                "text": t,
                "reason": "Nota al pie editorial - marcado false, revisar"
            })
    return blocks


def classify_ciudad_y_los_perros(blocks: list[dict]) -> list[dict]:
    for i, b in enumerate(blocks):
        t = _text(b)
        _id_block = _id(b)

        # Front matter editorial
        # blocks::1-5: synopsis/critical review
        if i <= 4:
            b["is_narrative"] = False
        # block::6: author name (portada)
        elif i == 5 and t == "Mario Vargas Llosa":
            b["is_narrative"] = False
        # block::7: title (portada)
        elif i == 6 and t == "La ciudad y los perros":
            b["is_narrative"] = False
        # block::8: ePub version
        elif i == 7 and _is_epub_version(t):
            b["is_narrative"] = False
        # block::9: converter
        elif i == 8 and "GONZALEZ" in t:
            b["is_narrative"] = False
        # block::10: copyright
        elif i == 9 and _is_copyright(t):
            b["is_narrative"] = False
        # block::11: ePub base
        elif i == 10 and _is_epub_version(t):
            b["is_narrative"] = False
        # block::12 "PRÓLOGO" → true (author's own prologue)
        # blocks::13-15: prologue text → true
        # block::16 "Fuschl, agosto de 1997" → true (part of prologue)
        # block::17 "PRIMERA PARTE" onwards → true

        # Everything else stays narrative (true)
    return blocks


def classify_metamorfosis(blocks: list[dict]) -> list[dict]:
    # Blocks 1-2: portada → false, rest narrative
    for i, b in enumerate(blocks):
        t = _text(b)
        if i == 0 and t == "La metamorfosis":
            b["is_narrative"] = False
        elif i == 1 and t == "Franz Kafka":
            b["is_narrative"] = False
    return blocks


def classify_tom_sawyer(blocks: list[dict]) -> list[dict]:
    for i, b in enumerate(blocks):
        t = _text(b)
        _id_block = _id(b)

        # block::1: title (portada) → false
        if i == 0 and "Las aventuras de Tom Sawyer" in t:
            b["is_narrative"] = False
        # block::2: author (portada) → false
        elif i == 1 and t == "Mark Twain":
            b["is_narrative"] = False
        # block::3: "Publicado: 1876" → false
        elif i == 2 and _is_publicado(t):
            b["is_narrative"] = False
        # block::4: "Índice de contenidos" → false
        elif i == 3 and "Índice" in t:
            b["is_narrative"] = False
        # blocks::5-15: TOC entries (Prefacio, chapter lists, Conclusión) → false
        elif 4 <= i <= 14:
            # Check TOC entries: "Prefacio", chapter ranges, "Conclusión"
            b["is_narrative"] = False
        # block::16 "Prefacio" → true (actual preface content)
        # blocks::17-18: preface text → true
        # block::19 "EL AUTOR. Hartford, 1876." → true (part of preface)
        # block::20 "Capítulo I" onwards → true
        # At end:
        # block::1852 "Conclusión" → true (actual conclusion chapter)
        # blocks::1853-1854: conclusion text → true
        # block::1855: Elejandria → false
        elif i >= len(blocks) - 3 and i <= len(blocks) - 1:
            if _is_elejandria_footer(t) or "Hitos" in t:
                b["is_narrative"] = False
            # block::1857 "Hitos" → false
    return blocks


def classify_matalache(blocks: list[dict]) -> list[dict]:
    for i, b in enumerate(blocks):
        t = _text(b)
        _id_block = _id(b)

        # Front matter: synopsis + editorial
        # blocks::1-15: synopsis → false
        if i <= 14:
            b["is_narrative"] = False
        # block::16: author name (portada) → false
        elif i == 15 and t == "Enrique López Albújar":
            b["is_narrative"] = False
        # block::17: title (portada) → false
        elif i == 16 and t == "Matalaché":
            b["is_narrative"] = False
        # block::18: ePub version → false
        elif i == 17 and _is_epub_version(t):
            b["is_narrative"] = False
        # block::19: converter → false
        elif i == 18 and "jugaor" in t:
            b["is_narrative"] = False
        # block::20: original title → false
        elif i == 19 and "Título original:" in t:
            b["is_narrative"] = False
        # block::21: copyright → false
        elif i == 20 and "Enrique López Albújar, 1928" in t:
            b["is_narrative"] = False
        # block::22: cover art → false
        elif i == 21 and "Arte de cubierta:" in t:
            b["is_narrative"] = False
        # block::23: editor digital → false
        elif i == 22 and _is_editorial_credit(t):
            b["is_narrative"] = False
        # block::24: ePub base → false
        elif i == 23 and _is_epub_version(t):
            b["is_narrative"] = False
        # block::25 "I" onwards → narrative → true

        # At end: author bio (blocks 4522..end, i.e. index 4521..end)
        # The author bio starts with "ENRIQUE LÓPEZ ALBÚJAR (Chiclayo...)"
        # The last narrative blocks are 4520-4521 ("EN SAN FRANCISCO..." and "•")
        elif i >= len(blocks) - 11:
            b["is_narrative"] = False
            DOUBTS.append({
                "book_id": "matalache_enrique_lopez_albujar",
                "id_block": _id_block,
                "text": t[:100],
                "reason": "Biografía del autor al final - marcado false, revisar"
            })
    return blocks


def classify_viaje(blocks: list[dict]) -> list[dict]:
    for i, b in enumerate(blocks):
        t = _text(b)
        _id_block = _id(b)

        # block::1 "Índice" → false
        if i == 0 and t == "Índice":
            b["is_narrative"] = False
        # block::2 "Información" → false (TOC item)
        elif i == 1 and t == "Información":
            b["is_narrative"] = False
        # blocks::3-47: TOC chapter list
        elif 2 <= i <= 46:
            # Chapter entries in TOC → false
            b["is_narrative"] = False
        # block::48: title portada → false
        elif i == 47 and t == "Viaje al centro de la Tierra":
            b["is_narrative"] = False
        # block::49: "Publicado: 1862 Fuente: Wikisource Traductor: Anónimo" → false
        elif i == 48 and _is_source_info(t):
            b["is_narrative"] = False
        # block::50: legal notice → false
        elif i == 49 and _is_legal_notice(t):
            b["is_narrative"] = False
        # block::51 "Capítulo I" onwards → narrative → true

        # At end: Elejandria footer
        # block::2357-2358: last 2 blocks
        elif i >= len(blocks) - 2:
            b["is_narrative"] = False
    return blocks


# ---------------------------------------------------------------------------
# Classifier registry
# ---------------------------------------------------------------------------

CLASSIFIERS = {
    "cronica_de_una_muerte_anunciada_gabriel_garcia_marquez": classify_cronica,
    "el_maravilloso_mago_de_oz_baum_lyman_frank": classify_mago_de_oz,
    "el_viejo_y_el_mar_ernest_hemingway": classify_viejo_y_el_mar,
    "la_ciudad_y_los_perros_mario_vargas_llosa": classify_ciudad_y_los_perros,
    "la_metamorfosis_franz_kafka": classify_metamorfosis,
    "las_aventuras_de_tom_sawyer_mark_twain": classify_tom_sawyer,
    "matalache_enrique_lopez_albujar": classify_matalache,
    "viaje_al_centro_de_la_tierra_julio_verne": classify_viaje,
}


def process_file(filepath: Path) -> dict:
    """Read, classify, and return modified JSON data."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    book_id = data["book_id"]
    blocks = data["blocks"]

    classifier = CLASSIFIERS.get(book_id)
    if classifier:
        blocks = classifier(blocks)
    else:
        print(f"  WARNING: No classifier for {book_id}")

    # General post-check: empty or very short residual blocks
    for b in blocks:
        t = _text(b)
        if len(t) == 0:
            b["is_narrative"] = False

    data["blocks"] = blocks
    return data


def main():
    global DOUBTS
    json_files = sorted(MASTER_DIR.glob("*.master.json"))
    print(f"Processing {len(json_files)} files...\n")

    for fp in json_files:
        print(f"  {fp.name}")
        data = process_file(fp)

        # Write corrected file
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    # Write doubts file
    doubts_path = MASTER_DIR / "doubts_for_review.json"
    with open(doubts_path, "w", encoding="utf-8") as f:
        json.dump(DOUBTS, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nDone! Processed {len(json_files)} files.")
    print(f"Doubts file: {doubts_path}")
    print(f"Blocks flagged for review: {len(DOUBTS)}")


if __name__ == "__main__":
    main()

