"""
Genera preguntas hipotéticas para TODOS los chunks de un libro usando LLM router (8B).
Procesa en tandas y escribe progresivamente.
"""
from __future__ import annotations

import json
import sys
import time
import argparse
import logging
from pathlib import Path

from companion.providers.nvidia_llm import NvidiaLLMProvider
from companion.config import settings

BATCH_SIZE = 15
MAX_TOKENS = 8192

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

PROMPT_TEMPLATE = """Eres un experto en literatura hispanoamericana. Genera preguntas de comprensión lectora para fragmentos de "{book_title}" de {book_author}.

Para CADA fragmento, genera EXACTAMENTE 5 preguntas:
1. DESCRIPTIVA (cómo es/ocurre algo)
2. FACTUAL (hecho/dato concreto)
3. CAUSA/CONSECUENCIA (por qué / qué resulta)
4. EMOCIÓN/RELACIÓN (sentimientos / relaciones entre personajes)
5. CONFLICTO/DECISIÓN/SIGNIFICADO (dilema, decisión, significado)

Si un tipo no aplica, reemplázalo con INFERENCIA o PREDICCIÓN.

Responde SOLO el JSON (sin markdown, sin backticks):
[
  {{"chunk_id": "ID_FRAGMENTO", "preguntas": ["P1","P2","P3","P4","P5"]}},
  ...
]

FRAGMENTOS:
{chunks_text}"""


def load_retrieval_file(path: Path) -> list[dict]:
    chunks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunks.append(json.loads(line))
    return chunks


def clean_json_response(response: str) -> str:
    response = response.strip()
    for prefix in ["```json", "```"]:
        if response.startswith(prefix):
            response = response[len(prefix):]
    for suffix in ["```"]:
        if response.endswith(suffix):
            response = response[:-len(suffix)]
    return response.strip()


def generate_batch(llm: NvidiaLLMProvider, batch: list[dict], book_title: str, book_author: str) -> list[dict]:
    parts = []
    for chunk in batch:
        parts.append(f"[FRAGMENTO {chunk['chunk_id']}]\n{chunk['text']}\n")

    prompt = PROMPT_TEMPLATE.format(
        book_title=book_title,
        book_author=book_author,
        chunks_text="\n".join(parts),
    )

    response = llm._retry(
        lambda: llm._client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=MAX_TOKENS,
        ).choices[0].message.content or ""
    )

    response = clean_json_response(response)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        # Try to extract JSON array from response
        import re
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        print(f"  ERROR parse. First 300 chars: {response[:300]}", flush=True)
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("retrieval_file", type=Path)
    parser.add_argument("output_file", type=Path)
    parser.add_argument("--resume", type=int, default=0, help="Reanudar desde chunk N (1-indexed)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    retrieval_path = args.retrieval_file
    output_path = args.output_file
    resume_from = args.resume
    batch_size = args.batch_size

    if not retrieval_path.exists():
        print(f"ERROR: No existe {retrieval_path}")
        sys.exit(1)

    print(f"Cargando {retrieval_path}...")
    all_chunks = load_retrieval_file(retrieval_path)
    total = len(all_chunks)
    print(f"Total chunks: {total}")

    if resume_from > 0:
        print(f"Reanudando desde chunk {resume_from}")
        all_chunks = all_chunks[resume_from - 1:]
        if output_path.exists():
            with open(output_path, encoding="utf-8") as f:
                existing = sum(1 for _ in f)
            print(f"  Output existente: {existing} lineas")

    book_meta = all_chunks[0]["metadata"]
    book_title = book_meta.get("title", "Desconocido")
    book_author = book_meta.get("author", "Desconocido")
    print(f"Libro: {book_title} - {book_author}")
    print(f"Tandas de {batch_size} chunks | Modelo: {settings.router_model}")

    llm = NvidiaLLMProvider(model=settings.router_model, temperature=0.2)

    total_batches = (len(all_chunks) + batch_size - 1) // batch_size
    processed = 0
    errors = 0

    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        chunk_nums = [c["chunk_id"].split("::")[-1] for c in batch]
        range_str = f"{chunk_nums[0]}-{chunk_nums[-1]}"

        sys.stdout.write(f"  [{batch_num:3d}/{total_batches}] chunks {range_str} ... ")
        sys.stdout.flush()

        try:
            results = generate_batch(llm, batch, book_title, book_author)
        except Exception as e:
            print(f"ERR: {e}", flush=True)
            results = []
            for chunk in batch:
                try:
                    single = generate_batch(llm, [chunk], book_title, book_author)
                    if single:
                        results.extend(single)
                    else:
                        raise ValueError("empty result")
                except Exception:
                    results.append({
                        "chunk_id": chunk["chunk_id"],
                        "preguntas": [
                            f"¿Qué sucede en este fragmento de {book_title}?",
                            f"¿Qué hecho concreto se narra aquí?",
                            f"¿Por qué ocurre lo narrado en este fragmento?",
                            f"¿Qué sentimientos o relaciones se muestran?",
                            f"¿Qué conflicto o decisión se presenta?",
                        ],
                    })

        if not results:
            print(f"VACIO!", flush=True)
            errors += 1
            continue

        # Write
        with open(output_path, "a", encoding="utf-8") as f:
            for item in results:
                qs = item.get("preguntas", item.get("hypothetical_questions", []))
                if len(qs) < 5:
                    qs = qs + [f"Pregunta {j+1} sobre el fragmento" for j in range(len(qs), 5)]
                elif len(qs) > 5:
                    qs = qs[:5]
                line = {"chunk_id": item["chunk_id"], "hypothetical_questions": qs}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

        processed += len(batch)
        print(f"OK  ({processed}/{total})", flush=True)

    # Final verification
    with open(output_path, encoding="utf-8") as f:
        final_lines = sum(1 for _ in f)
    print(f"\n=== COMPLETADO ===")
    print(f"Output: {output_path}")
    print(f"Lineas: {final_lines} / Esperadas: {total}")
    if final_lines == total:
        print("OK!")
    else:
        print(f"ADVERTENCIA: diferencia de {total - final_lines}")


if __name__ == "__main__":
    main()
