"""
Regenera preguntas hipotéticas para Las aventuras de Tom Sawyer.
5 preguntas por chunk (descriptiva, factual, causa/cons, emoción/relación, conflicto/decisión/significado).
Usa el content LLM (70B) en lotes de 8 chunks con save incremental.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from openai import OpenAI
from companion.config import settings

RETRIEVAL_FILE = Path("data/outputs/retrieval/las_aventuras_de_tom_sawyer_mark_twain.retrieval.jsonl")
OUTPUT_FILE = Path("data/outputs/hypotheticals/las_aventuras_de_tom_sawyer_mark_twain.hypotheticals.jsonl")

BATCH_SIZE = 8
MAX_TOKENS = 4096
DELAY = 3.0

PROMPT_TEMPLATE = """Eres un profesor de literatura generando preguntas de comprensión lectora para alumnos de secundaria sobre "Las aventuras de Tom Sawyer" de Mark Twain.

A continuación hay {n} fragmentos del texto, cada uno identificado con un ID [CHUNK_X].

Para CADA fragmento, genera EXACTAMENTE 5 preguntas en español:
  1. DESCRIPTIVA: ¿Cómo es...? ¿Qué aspecto tiene...? (cómo es algo o alguien)
  2. FACTUAL: ¿Qué pasó...? ¿Quién hizo...? ¿Dónde...? (hecho concreto del texto)
  3. CAUSA/CONSECUENCIA: ¿Por qué...? ¿Qué provocó...? (causa o consecuencia)
  4. EMOCIÓN/RELACIÓN: ¿Cómo se siente...? ¿Qué relación hay entre...? (sentimientos, vínculos)
  5. CONFLICTO/DECISIÓN/SIGNIFICADO: ¿Qué dilema...? ¿Qué significa...? (dilema, elección, sentido)

Reglas:
- Preguntas naturales, sin inventar hechos, sin spoilers de capítulos futuros
- Breves (una oración cada una)
- Si un tipo no aplica al fragmento, genera otro tipo diferente (INFERENCIA, PREDICCIÓN)

Responde ÚNICAMENTE con un objeto JSON donde cada clave es el ID del chunk (CHUNK_1, CHUNK_2, ...) y el valor es un array de exactamente 5 strings. Sin explicaciones ni markdown.

Ejemplo de formato:
{{"CHUNK_1": ["¿Cómo es el personaje principal?", "¿Qué hizo Tom al entrar a casa?", "¿Por qué la tía Polly se enfadó?", "¿Cómo se siente Tom después del castigo?", "¿Qué dilema enfrenta Tom en esta situación?"], "CHUNK_2": [...]}}

FRAGMENTOS:
{chunks_text}"""


def load_chunks() -> list[dict]:
    chunks = []
    with open(RETRIEVAL_FILE, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunks.append(json.loads(line))
    return chunks


def parse_response(response: str, label_map: dict[str, str]) -> dict[str, list[str]]:
    """Extrae {chunk_id_real: [5 preguntas]} de la respuesta JSON del LLM."""
    response = response.strip()
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
        cid = label_map.get(key)
        if cid and isinstance(val, list) and all(isinstance(q, str) for q in val):
            qs = [q.strip() for q in val[:5]]
            while len(qs) < 5:
                qs.append(qs[-1] if qs else "?")
            if all(qs):
                result[cid] = qs
    return result


def save_results(questions: dict[str, list[str]], chunk_order: list[str]) -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for cid in chunk_order:
            qs = questions.get(cid, [])
            f.write(
                json.dumps(
                    {"chunk_id": cid, "hypothetical_questions": qs},
                    ensure_ascii=False,
                )
                + "\n"
            )


def main():
    print(f"Cargando {RETRIEVAL_FILE}...")
    chunks = load_chunks()
    total = len(chunks)
    print(f"Total chunks: {total}")

    chunk_order = [c["chunk_id"] for c in chunks]

    # Load existing if any
    questions: dict[str, list[str]] = {}
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                cid = entry.get("chunk_id", "")
                qs = entry.get("hypothetical_questions", [])
                if cid and len(qs) == 5:
                    questions[cid] = qs
        print(f"  Resume: {len(questions)} chunks ya tienen 5 preguntas")
    else:
        print(f"  Output nuevo: {OUTPUT_FILE}")

    # Find pending chunks
    pending = [(i, c) for i, c in enumerate(chunks) if c["chunk_id"] not in questions]
    if not pending:
        print("Todos los chunks ya tienen 5 preguntas. Nada que hacer.")
        return

    batches = [pending[i:i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    print(f"  Pendientes: {len(pending)} chunks en {len(batches)} lotes de {BATCH_SIZE}")

    # Init LLM client
    client = OpenAI(
        base_url=settings.nvidia_base_url,
        api_key=settings.nvidia_api_key,
    )
    model = settings.content_model
    print(f"  Modelo: {model} | Delay: {DELAY}s | Max tokens: {MAX_TOKENS}")

    errors = 0
    for batch_idx, batch in enumerate(batches):
        # Build prompt
        chunks_text_parts = []
        label_map: dict[str, str] = {}
        for j, (orig_idx, chunk) in enumerate(batch):
            label = f"CHUNK_{j + 1}"
            label_map[label] = chunk["chunk_id"]
            chunks_text_parts.append(f"[{label}]\n{chunk['text']}")

        prompt = PROMPT_TEMPLATE.format(
            n=len(batch),
            chunks_text="\n\n---\n\n".join(chunks_text_parts),
        )

        # Display progress
        chunk_nums = [str(orig_idx + 1) for orig_idx, _ in batch]
        range_str = f"{chunk_nums[0]}-{chunk_nums[-1]}"
        sys.stdout.write(
            f"  [{batch_idx + 1:3d}/{len(batches)}] chunks {range_str} ... "
        )
        sys.stdout.flush()

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=MAX_TOKENS,
            )
            content = resp.choices[0].message.content or ""
            batch_results = parse_response(content, label_map)
        except Exception as exc:
            print(f"ERR: {exc}", flush=True)
            time.sleep(DELAY * 3)
            errors += 1
            continue

        batch_count = 0
        for cid, qs in batch_results.items():
            if len(qs) == 5:
                questions[cid] = qs
                batch_count += 1

        if batch_count == 0:
            print(f"EMPTY (respuesta: {content[:120]}...)", flush=True)
            errors += 1
        else:
            ok_total = len(questions)
            print(f"OK ({batch_count}/{len(batch)} → total {ok_total}/{total})", flush=True)

        # Save incrementally every 2 batches
        if (batch_idx + 1) % 2 == 0:
            save_results(questions, chunk_order)

        time.sleep(DELAY)

    # Final save
    save_results(questions, chunk_order)

    # Final count
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        final_lines = sum(1 for _ in f)

    complete = sum(1 for cid in chunk_order if cid in questions and len(questions[cid]) == 5)
    print(f"\n=== COMPLETADO ===")
    print(f"  Output: {OUTPUT_FILE}")
    print(f"  Lineas: {final_lines} / Esperadas: {total}")
    print(f"  Chunks con 5 preguntas: {complete}/{total}")
    print(f"  Errores: {errors}")
    if final_lines == total:
        print("  OK - todas las líneas corresponden")
    else:
        print(f"  WARNING: diferencia de {total - final_lines} líneas")


if __name__ == "__main__":
    main()
