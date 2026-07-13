"""
Benchmark de retrieval puro para La metamorfosis y El mago de Oz.
Métricas: hits@K, precision@K, recall@K, MRR, NDCG, latencia.
Solo mide la búsqueda vectorial (embedding + top-K), sin generación LLM.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent


# ── Ground truth: (book_id, query, expected_chunk_indexes) ──────────
QUERIES: list[tuple[str, str, list[int]]] = [
    # ── La metamorfosis ──
    ("la_metamorfosis_franz_kafka", "En qué se convirtió Gregorio Samsa al despertar", [1]),
    ("la_metamorfosis_franz_kafka", "Por qué Gregorio odia su trabajo de viajante", [1, 2, 3]),
    ("la_metamorfosis_franz_kafka", "Cómo reacciona la madre al escuchar la nueva voz de Gregorio", [5, 6, 7]),
    ("la_metamorfosis_franz_kafka", "Quién es el apoderado y qué le reclama a Gregorio", [12, 13, 14, 15, 16]),
    ("la_metamorfosis_franz_kafka", "Qué hace Gregorio para abrir la puerta de su habitación", [21, 22]),
    ("la_metamorfosis_franz_kafka", "Cómo reacciona el padre cuando ve a Gregorio salir de su cuarto", [22, 23, 27, 29, 30]),
    ("la_metamorfosis_franz_kafka", "Qué comida le trae Grete a Gregorio y cómo reacciona él", [36, 37]),
    ("la_metamorfosis_franz_kafka", "Qué descubre Gregorio sobre las finanzas familiares", [41, 42, 43, 44]),
    ("la_metamorfosis_franz_kafka", "Por qué Grete y la madre deciden vaciar la habitación", [49, 50, 53, 54]),
    ("la_metamorfosis_franz_kafka", "Qué hace Gregorio para proteger el cuadro de la mujer", [55, 56, 57]),
    ("la_metamorfosis_franz_kafka", "Cómo cambia el padre físicamente en el capítulo 2", [60, 61, 62]),
    ("la_metamorfosis_franz_kafka", "Qué le lanza el padre a Gregorio y qué consecuencias tiene", [63, 64]),
    ("la_metamorfosis_franz_kafka", "Quiénes son los huéspedes y cómo tratan a la familia Samsa", [74, 75, 76, 77]),
    ("la_metamorfosis_franz_kafka", "Qué sucede cuando Grete toca el violín y Gregorio sale al comedor", [76, 77, 78, 79, 80]),
    ("la_metamorfosis_franz_kafka", "Qué dice Grete sobre Gregorio antes de su muerte", [82, 83, 84, 85]),
    ("la_metamorfosis_franz_kafka", "Cómo muere Gregorio y cómo reacciona la familia", [87, 88, 89, 90]),

    # ── El maravilloso mago de Oz ──
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Dónde vive Dorothy y cómo llega a Oz", [1, 2, 3, 4, 5]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Quién es la Bruja Buena del Norte y qué le da a Dorothy", [6, 7, 8, 9, 10]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Qué son los zapatos de plata y por qué son importantes", [8, 9, 13, 14]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Cómo conoce Dorothy al Espantapájaros y qué desea él", [18, 19, 20]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Por qué el Espantapájaros quiere un cerebro", [23, 24, 25]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Cómo encuentran al Leñador de Hojalata y por qué está oxidado", [28, 29, 30]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Qué le pasó al Leñador con la Bruja Maligna del Este", [30, 31, 32, 33, 34]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Cómo conocen al León Cobarde y qué desea", [36, 37, 38, 39]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Qué peligro enfrentan en el campo de amapolas", [53, 54, 55]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Quién es la Reina de los Ratones y cómo ayuda al grupo", [56, 57, 58, 59, 60]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Cómo es la Ciudad Esmeralda y qué impresión causa", [65, 66, 67, 68, 69]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Qué condiciones pone Oz para conceder los deseos del grupo", [73, 74, 75, 76]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Cómo derrotan a la Bruja Maligna del Oeste", [84, 85, 86, 87, 88, 89, 90, 91, 92, 95, 96]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Qué descubre el grupo sobre el verdadero Oz", [112, 113, 114, 115, 116, 117]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Cómo obtienen el Espantapájaros, el Leñador y el León lo que deseaban", [119, 120, 121, 122, 123, 124]),
    ("el_maravilloso_mago_de_oz_baum_lyman_frank", "Cómo regresa Dorothy a Kansas", [152, 153, 154, 155, 156]),
]

K_VALUES = [1, 3, 5, 10]


def dcg_at_k(relevances: list[int], k: int) -> float:
    """Discounted Cumulative Gain at K."""
    import math
    dcg = 0.0
    for i, rel in enumerate(relevances[:k]):
        dcg += (2 ** rel - 1) / math.log2(i + 2)
    return dcg


def ndcg_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    """Normalized DCG at K. Relevance = 1 if chunk in relevant set, else 0."""
    rels = [1 if c in relevant else 0 for c in retrieved[:k]]
    dcg = dcg_at_k(rels, k)
    ideal_rels = sorted([1] * min(len(relevant), k) + [0] * max(0, k - len(relevant)), reverse=True)
    idcg = dcg_at_k(ideal_rels, k)
    return dcg / idcg if idcg > 0 else 0.0


def precision_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    return sum(1 for c in retrieved[:k] if c in relevant) / k


def recall_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    return sum(1 for c in retrieved[:k] if c in relevant) / len(relevant) if relevant else 0.0


def mean_reciprocal_rank(results: list[list[int]], relevants: list[set[int]]) -> float:
    mrr = 0.0
    for retrieved, relevant in zip(results, relevants):
        for rank, chunk in enumerate(retrieved, 1):
            if chunk in relevant:
                mrr += 1.0 / rank
                break
    return mrr / len(results) if results else 0.0


def run() -> None:
    from companion.embedders.factory import get_embedder
    from companion.vector_store.chroma_store import ChromaVectorStore
    from companion.config import settings

    print("Cargando embedder...", end=" ", flush=True)
    t0 = time.perf_counter()
    embedder = get_embedder()
    store = ChromaVectorStore(persist_dir=settings.chroma_persist_dir)
    load_time = time.perf_counter() - t0
    print(f"{load_time:.1f}s\n")

    all_retrieved: list[list[int]] = []
    all_relevant: list[set[int]] = []
    per_query_results: list[dict] = []
    latencies: list[float] = []

    max_k = max(K_VALUES)
    total = len(QUERIES)

    for i, (book_id, query, expected) in enumerate(QUERIES, 1):
        book_label = "Meta" if "kafka" in book_id else "Oz"
        print(f"[{i:2d}/{total}] {book_label}: {query[:80]}...", end=" ", flush=True)

        t_start = time.perf_counter()
        query_vec = embedder.embed(query)
        docs = store.search(query_vec, variant=book_id, top_k=max_k)
        elapsed = time.perf_counter() - t_start
        latencies.append(elapsed)

        retrieved = [int(d.chunk_id.rsplit("::", 1)[-1]) for d in docs]
        relevant = set(expected)
        all_retrieved.append(retrieved)
        all_relevant.append(relevant)

        # Per-K metrics
        k_metrics = {}
        for k in K_VALUES:
            hits_k = sorted(retrieved[:k])
            k_metrics[f"hits@{k}"] = hits_k
            k_metrics[f"hit@{k}"] = any(r in relevant for r in retrieved[:k])
            k_metrics[f"precision@{k}"] = round(precision_at_k(retrieved, relevant, k), 3)
            k_metrics[f"recall@{k}"] = round(recall_at_k(retrieved, relevant, k), 3)
            k_metrics[f"ndcg@{k}"] = round(ndcg_at_k(retrieved, relevant, k), 3)

        hit3 = k_metrics["hit@3"]
        hit_mark = "HIT" if hit3 else "MISS"
        print(f"{elapsed:.1f}s | {hit_mark} | top3={k_metrics['hits@3']} | q={relevant}")

        per_query_results.append({
            "book": book_label,
            "query": query,
            "time_s": round(elapsed, 2),
            "expected": sorted(relevant),
            **k_metrics,
        })

    # ── Aggregate metrics ──
    print("\n" + "=" * 80)
    print("RESULTADOS AGREGADOS")
    print("=" * 80)

    hits_per_k = {k: sum(1 for r in per_query_results if r[f"hit@{k}"]) for k in K_VALUES}
    prec_per_k = {k: statistics.mean([r[f"precision@{k}"] for r in per_query_results]) for k in K_VALUES}
    rec_per_k = {k: statistics.mean([r[f"recall@{k}"] for r in per_query_results]) for k in K_VALUES}
    ndcg_per_k = {k: statistics.mean([r[f"ndcg@{k}"] for r in per_query_results]) for k in K_VALUES}
    mrr = mean_reciprocal_rank(all_retrieved, all_relevant)

    for k in K_VALUES:
        print(f"  hits@{k:2d}:  {hits_per_k[k]:2d}/{total} ({hits_per_k[k]/total*100:.0f}%)")
    print(f"  MRR:     {mrr:.3f}")
    print()
    for k in K_VALUES:
        print(f"  precision@{k:2d}: {prec_per_k[k]:.3f}")
    for k in K_VALUES:
        print(f"  recall@{k:2d}:    {rec_per_k[k]:.3f}")
    for k in K_VALUES:
        print(f"  nDCG@{k:2d}:     {ndcg_per_k[k]:.3f}")
    print()
    print(f"  Latencia media:  {statistics.mean(latencies):.1f}s")
    print(f"  Latencia min:    {min(latencies):.1f}s")
    print(f"  Latencia max:    {max(latencies):.1f}s")
    print(f"  Latencia p50:    {statistics.median(latencies):.1f}s")

    # ── Book-level breakdown ──
    for book_label in ["Meta", "Oz"]:
        book_results = [r for r in per_query_results if r["book"] == book_label]
        book_hits3 = sum(1 for r in book_results if r["hit@3"])
        book_mrr = mean_reciprocal_rank(
            [[c for c in r["hits@3"] if c in set(r["expected"])] for r in book_results],
            [set(r["expected"]) for r in book_results],
        ) if book_results else 0
        book_rec3 = statistics.mean([r["recall@3"] for r in book_results]) if book_results else 0
        print(f"\n  --- {book_label} ({len(book_results)} queries) ---")
        print(f"  hits@3: {book_hits3}/{len(book_results)} | MRR: {book_mrr:.3f} | recall@3: {book_rec3:.3f}")

    # Per-query detail table
    print("\n" + "=" * 80)
    print("DETALLE POR QUERY")
    print(f"{'#':>3} {'Libro':>5} {'t(s)':>5} {'hit@3':>5} {'prec@3':>7} {'rec@3':>6} {'ndcg@3':>6}  Query")
    print("-" * 80)
    for i, r in enumerate(per_query_results, 1):
        print(f"{i:3d} {r['book']:>5} {r['time_s']:5.1f} "
              f"{'HIT' if r['hit@3'] else 'MISS':>5} "
              f"{r['precision@3']:7.3f} {r['recall@3']:6.3f} {r['ndcg@3']:6.3f}  "
              f"{r['query'][:65]}")

    # Save detailed results
    out = ROOT / "data" / "outputs" / "benchmark_retrieval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "embedder": "intfloat/multilingual-e5-base",
            "load_time_s": round(load_time, 1),
            "total_queries": total,
            "k_values": K_VALUES,
            "aggregate": {
                f"hits@{k}": { "count": hits_per_k[k], "pct": round(hits_per_k[k]/total*100, 1) }
                for k in K_VALUES
            },
            "mrr": round(mrr, 3),
            **{f"precision_mean@{k}": round(prec_per_k[k], 3) for k in K_VALUES},
            **{f"recall_mean@{k}": round(rec_per_k[k], 3) for k in K_VALUES},
            **{f"ndcg_mean@{k}": round(ndcg_per_k[k], 3) for k in K_VALUES},
            "latency": {
                "mean_s": round(statistics.mean(latencies), 1),
                "median_s": round(statistics.median(latencies), 1),
                "min_s": round(min(latencies), 1),
                "max_s": round(max(latencies), 1),
            },
            "per_query": per_query_results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nResultados guardados en: {out}")


if __name__ == "__main__":
    run()
