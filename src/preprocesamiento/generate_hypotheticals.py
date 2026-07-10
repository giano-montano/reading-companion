"""
generate_hypotheticals.py — Genera preguntas hipotéticas con el content LLM (70B).

Procesa chunks en lotes de 5 por llamada API para sortear rate limits.
Genera 5 preguntas por chunk:
  1. DESCRIPTIVA  2. FACTUAL  3. CAUSA/CONSECUENCIA
  4. EMOCIÓN/RELACIÓN  5. CONFLICTO/DECISIÓN/SIGNIFICADO

Uso:
  .venv\\Scripts\\python.exe -m preprocesamiento.generate_hypotheticals --book_id viaje_al_centro_de_la_tierra_julio_verne
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RETRIEVAL_DIR = ROOT / "data" / "outputs" / "retrieval"
HYPOTHETICALS_DIR = ROOT / "data" / "outputs" / "hypotheticals"

BATCH_SIZE = 5

BATCH_PROMPT = """Eres un profesor generando preguntas de comprensión lectora para alumnos de secundaria sobre "{title}" de {author}.

A continuación hay {n} fragmentos del texto, cada uno identificado con un ID [CHUNK_X].
Para CADA fragmento, genera EXACTAMENTE 5 preguntas en español:
  1. DESCRIPTIVA (cómo es algo o alguien)
  2. FACTUAL (hecho concreto del texto)
  3. CAUSA/CONSECUENCIA (por qué o qué resulta)
  4. EMOCIÓN/RELACIÓN (sentimientos, vínculos)
  5. CONFLICTO/DECISIÓN/SIGNIFICADO (dilema, elección, sentido)

Responde ÚNICAMENTE con un objeto JSON donde cada clave es el ID del chunk y el valor es un array de 5 strings. Sin explicaciones.

Ejemplo:
{{"CHUNK_1": ["¿Pregunta 1?", "¿Pregunta 2?", "¿Pregunta 3?", "¿Pregunta 4?", "¿Pregunta 5?"], "CHUNK_2": [...]}}

FRAGMENTOS:
{chunks_text}"""


def load_chunks(book_id: str) -> list[dict]:
    rpath = RETRIEVAL_DIR / f"{book_id}.retrieval.jsonl"
    if not rpath.exists():
        raise FileNotFoundError(f"No encontrado: {rpath}")
    chunks = []
    with open(rpath, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunks.append(json.loads(line))
    return chunks


def load_existing(book_id: str) -> dict[str, list[str]]:
    hpath = HYPOTHETICALS_DIR / f"{book_id}.hypotheticals.jsonl"
    if not hpath.exists():
        return {}
    questions: dict[str, list[str]] = {}
    with open(hpath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            cid = entry.get("chunk_id", "")
            qs = entry.get("hypothetical_questions", [])
            if cid and len(qs) == 5:
                questions[cid] = qs
    return questions


def save_all(book_id: str, questions: dict[str, list[str]], chunk_order: list[str]) -> None:
    hpath = HYPOTHETICALS_DIR / f"{book_id}.hypotheticals.jsonl"
    HYPOTHETICALS_DIR.mkdir(parents=True, exist_ok=True)
    with open(hpath, "w", encoding="utf-8") as f:
        for cid in chunk_order:
            qs = questions.get(cid, [])
            f.write(json.dumps({"chunk_id": cid, "hypothetical_questions": qs},
                               ensure_ascii=False) + "\n")


def parse_batch_response(response: str) -> dict[str, list[str]]:
    """Extrae {chunk_id: [5 questions]} de la respuesta JSON del LLM."""
    response = response.strip()
    # Encontrar el objeto JSON más externo
    start = response.find("{")
    end = response.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        parsed = json.loads(response[start:end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, val in parsed.items():
        if isinstance(val, list) and all(isinstance(q, str) for q in val):
            # Normalizar key: CHUNK_1 -> chunk_id original
            cid = key.replace("CHUNK_", "chunk_")
            result[key] = val[:5]
    return result


def build_chunk_label(idx: int) -> str:
    """CHUNK_1, CHUNK_2, ..."""
    return f"CHUNK_{idx}"


def generate(book_id: str, delay: float = 8.0) -> int:
    from companion.providers.factory import get_content_llm

    chunks = load_chunks(book_id)
    total = len(chunks)
    print(f"Cargados {total} chunks de {book_id}")

    existing = load_existing(book_id)
    if existing:
        print(f"Resume: {len(existing)} chunks ya tienen 5 preguntas")

    first_meta = chunks[0].get("metadata", {}) if chunks else {}
    title = first_meta.get("title", book_id)
    author = first_meta.get("author", "desconocido")

    questions: dict[str, list[str]] = dict(existing)
    chunk_order: list[str] = [c.get("chunk_id", "") for c in chunks]

    llm = get_content_llm()

    # Agrupar chunks pendientes en lotes
    pending = [(i, c) for i, c in enumerate(chunks) if c.get("chunk_id") not in questions]
    batches = [pending[i:i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]

    processed = 0
    for batch_idx, batch in enumerate(batches):
        # Construir el prompt del lote
        chunks_text_parts = []
        label_map: dict[str, str] = {}  # CHUNK_X -> chunk_id real
        for j, (orig_idx, chunk) in enumerate(batch):
            label = build_chunk_label(j + 1)
            label_map[label] = chunk.get("chunk_id", "")
            chunks_text_parts.append(f"[{label}]\n{chunk.get('text', '')}")

        prompt = BATCH_PROMPT.format(
            title=title,
            author=author,
            n=len(batch),
            chunks_text="\n\n---\n\n".join(chunks_text_parts),
        )

        try:
            response = llm.complete(prompt)
            batch_results = parse_batch_response(response)
        except Exception as exc:
            print(f"  ERROR lote {batch_idx+1}/{len(batches)}: {exc}", file=sys.stderr)
            time.sleep(delay * 2)
            continue

        # Mapear resultados a chunk_ids reales
        batch_count = 0
        for label, qs in batch_results.items():
            cid = label_map.get(label)
            if cid and len(qs) >= 3:
                while len(qs) < 5:
                    qs.append(qs[-1] if qs else "?")
                questions[cid] = qs[:5]
                batch_count += 1

        processed += batch_count

        # Guardar incremental cada 2 lotes
        if (batch_idx + 1) % 2 == 0:
            save_all(book_id, questions, chunk_order)
            print(f"  Progreso: {len(questions)}/{total} (lote {batch_idx+1}/{len(batches)})")

        time.sleep(delay)

    # Guardado final
    save_all(book_id, questions, chunk_order)
    complete = sum(1 for cid in chunk_order if cid in questions and len(questions[cid]) == 5)
    print(f"\nCompletado: {complete}/{total} chunks con 5 preguntas")
    print(f"Archivo: {HYPOTHETICALS_DIR / f'{book_id}.hypotheticals.jsonl'}")
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera preguntas hipotéticas en lotes")
    parser.add_argument("--book_id", type=str, required=True)
    parser.add_argument("--delay", type=float, default=8.0)
    args = parser.parse_args()
    generate(args.book_id, delay=args.delay)


if __name__ == "__main__":
    main()
