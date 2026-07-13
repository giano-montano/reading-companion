"""
Benchmark rapido de QA-RAG: latencia y calidad de respuesta.

Mide tiempos de embedding, retrieval, y generacion LLM para
un conjunto de preguntas de prueba sobre distintos libros.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Preguntas de prueba: (book_id, query, pregunta_esperada_en_chunk_aproximado)
BENCHMARK_QUERIES = [
    ("el_viejo_y_el_mar_ernest_hemingway", "Como describen al viejo Santiago fisicamente?", [1]),
    ("el_viejo_y_el_mar_ernest_hemingway", "Por que los padres del muchacho no lo dejaban pescar con Santiago?", [1, 2]),
    ("el_viejo_y_el_mar_ernest_hemingway", "Que relacion tienen Santiago y Manolin?", [2, 4, 5, 6]),
    ("la_metamorfosis_franz_kafka", "En que se convirtio Gregorio Samsa?", [1]),
    ("la_metamorfosis_franz_kafka", "Como reacciona la familia de Gregorio al verlo transformado?", [10, 15]),
    ("la_metamorfosis_franz_kafka", "Por que Gregorio se preocupa por llegar tarde al trabajo?", [1, 2, 3]),
    ("cronica_de_una_muerte_anunciada_gabriel_garcia_marquez", "Quienes son los hermanos Vicario?", [20, 21]),
    ("cronica_de_una_muerte_anunciada_gabriel_garcia_marquez", "Por que quieren matar a Santiago Nasar?", [27, 28, 55]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Quien es Dorothy y donde vive?", [1, 2]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Como llega Dorothy a la tierra de Oz?", [5, 10]),
]


def run_benchmark() -> None:
    from companion.agent.state import AgentState
    from companion.agent.tools.contracts import ReadingState
    from companion.agent.orchestrator import QaRagOrchestrator
    from companion.embedders.factory import get_embedder
    from companion.vector_store.chroma_store import ChromaVectorStore
    from companion.providers.factory import get_router_llm
    from companion.config import settings

    print("Cargando modelo de embeddings...\n")
    t0 = time.perf_counter()
    embedder = get_embedder()
    store = ChromaVectorStore(persist_dir=settings.chroma_persist_dir)
    llm = get_router_llm()
    orch = QaRagOrchestrator(embedder=embedder, vector_store=store, llm=llm, top_k=3)
    load_time = time.perf_counter() - t0
    print(f"Setup: {load_time:.1f}s\n")

    results = []
    total_queries = len(BENCHMARK_QUERIES)

    for i, (book_id, query, expected_chunks) in enumerate(BENCHMARK_QUERIES, 1):
        print(f"[{i}/{total_queries}] {book_id.split('_')[0]}: {query[:70]}...")
        t_start = time.perf_counter()

        result = orch.run(
            query=query,
            agent_state=AgentState(),
            book_id=book_id,
            reading_state=ReadingState(max_progress_chunk_index=0),
        )

        elapsed = time.perf_counter() - t_start

        retrieved_indexes = sorted(
            int(c.chunk_id.rsplit("::", 1)[-1]) for c in result.citations
        )
        hit = any(ec in retrieved_indexes for ec in expected_chunks)
        hit_str = "HIT" if hit else "MISS"

        msg_preview = result.message[:120].replace("\n", " ")
        print(f"       {elapsed:.1f}s | {hit_str} | chunks={retrieved_indexes} | {msg_preview}...")
        print()

        results.append({
            "book": book_id.split("_")[0],
            "query": query,
            "time_s": round(elapsed, 2),
            "answered": result.answered,
            "hit": hit,
            "retrieved_chunks": retrieved_indexes,
            "expected_chunks": expected_chunks,
            "message": result.message,
        })

    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    times = [r["time_s"] for r in results]
    hits = sum(1 for r in results if r["hit"])
    answered = sum(1 for r in results if r["answered"])
    print(f"  Preguntas: {total_queries}")
    print(f"  Respondidas: {answered}/{total_queries}")
    print(f"  Hits (chunk esperado en top-3): {hits}/{total_queries}")
    print(f"  Latencia media: {sum(times)/len(times):.1f}s")
    print(f"  Latencia min/max: {min(times):.1f}s / {max(times):.1f}s")

    # Save detailed results
    out = ROOT / "data" / "outputs" / "benchmark_qa_rag.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "model": "router-8b",
            "load_time_s": round(load_time, 1),
            "total_queries": total_queries,
            "hits": hits,
            "answered": answered,
            "avg_latency_s": round(sum(times)/len(times), 1),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nResultados guardados en: {out}")


if __name__ == "__main__":
    run_benchmark()
