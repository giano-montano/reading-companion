# Handoff — API de chat (SSE) + imágenes async + intent IMAGEN

**Fecha:** 2026-07-10
**Autor:** agente de Giano
**Para:** Chang / Rodri + sus agentes
**Depende de:** [`2026-07-10-qa-rag-implementation.md`](2026-07-10-qa-rag-implementation.md),
[`2026-07-08-pipeline-consolidation.md`](2026-07-08-pipeline-consolidation.md)

## Qué se construyó

Se **expuso** el pipeline QA-RAG (que dejó Rodri) al frontend y se conectó todo
por un endpoint de chat guiado por el router, más el patrón async de imágenes.

### Endpoints nuevos / cambiados

| Método | Ruta | Estado |
|---|---|---|
| `POST` | `/api/chat` | **NUEVO** — router → tool, responde SSE |
| `POST` | `/api/images` | **NUEVO** — encola job de imagen (202) |
| `GET`  | `/api/images/{job_id}` | **NUEVO** — poll del job |
| `GET`  | `/api/books/{id}/reader` | **FIX** — leía `reader/`, los archivos están en `readers/` |

### Archivos nuevos

```
src/companion/api/deps.py          singletons (E5, Chroma, orchestrator, router) — se construyen 1 vez
src/companion/api/chat.py          POST /api/chat (StreamingResponse text/event-stream)
src/companion/api/images.py        POST /api/images + GET /api/images/{id}
src/companion/agent/runtime.py     AgentRuntime: decisión del router → eventos SSE
src/companion/scope/catalog.py     ChunkCatalog (desde retrieval.jsonl) para scope de imágenes
src/companion/images/jobs.py       job store en memoria (thread-safe)
src/companion/images/runner.py     worker de imagen compartido (BackgroundTasks + thread)
```

### Archivos modificados

| Archivo | Cambio |
|---|---|
| `agent/tools/contracts.py` | `ToolName += "imagen"` (ver ⚠️ abajo) |
| `agent/router.py` | etiqueta `IMAGEN` en clasificador + `_LABEL_TO_TOOL` + `_parse_label` |
| `api/server.py` | registra chat/images routers + `warmup()` en startup |
| `api/books.py` | `READER_DIR` → `data/outputs/readers/` |
| `.env` | `EMBEDDING_MODEL=intfloat/multilingual-e5-base` (ver ⚠️ abajo) |

## ⚠️ Cambios que os afectan (superficie compartida)

1. **`contracts.py` — `ToolName` ganó `"imagen"`.** Es **aditivo**: `imagen` es
   solo un destino de enrutado (job async de ilustración), NO tiene variante
   `ToolInput`/`ToolOutput`, así que NO aparece en las uniones discriminadas.
   Nada de lo vuestro se rompe; solo no asumáis que `ToolName` tiene 4 valores.

2. **`.env` — `EMBEDDING_MODEL` debe ser `intfloat/multilingual-e5-base`.** La
   Chroma está indexada a 768d (E5). Si el embedder carga MiniLM (384d) el
   retrieval revienta con `dimension 768, got 384`. Además había una env var del
   SO vieja pisando el `.env` (no persistente); si veis ese error, limpiadla en
   la terminal antes de levantar el server.

3. **Los readers están en `data/outputs/readers/`** (plural), no `reader/`.

## Eje anti-spoiler (unificado)

Se respeta el eje que fijó Rodri: **`max_progress_chunk_index`** (el entero al
final de `book::chunk::N`). El `ChunkCatalog.up_to_index()` de imágenes usa el
mismo criterio, así que "hasta el máximo" y el gate de QA-RAG son coherentes.

## Contrato SSE de `/api/chat`

Responde SIEMPRE `text/event-stream`. El `event:` discrimina la rama:

```
event: route      {"tool":"qa_rag"|"imagen"|"clarify"|"resumir"|"grafo"|"evaluacion"}
event: token      {"delta":"..."}                 # qa_rag: texto incremental
event: citations  {"citations":[...],"answered":bool,"ok":bool}   # qa_rag terminal
event: clarify    {"clarification":"...","clarify_count":n}
event: image_job  {"job_id":"...","poll_url":"/api/images/{id}"}   # imagen
event: notice     {"tool":"...","message":"..."}   # ramas no implementadas
event: error      {"message":"..."}                # fallo controlado
event: done       {}                               # siempre al final
```

> Streaming de QA-RAG **simulado** por ahora: se genera la respuesta completa
> (70B, ~90s) y se trocea en `token`. Cambiar a streaming real solo toca
> `runtime._stream_qa_rag`, no el contrato de eventos.

## Diferido (no implementado)

- **RESUMIR / GRAFO** → devuelven `notice` "no disponible" (GRAFO necesita
  `graph.json`, inexistente — `jobs/graph_job.py` sigue vacío).
- **EVALUACIÓN** → `notice` stub. Se fuerza vía `pending_question`, pero no hay
  lógica de participación aún.
- **Streaming real de tokens** (añadir `stream_chat` al provider NVIDIA).

## Cómo levantar

```powershell
.venv\Scripts\python.exe -m uvicorn companion.api.server:app --reload --port 8000
```

El `startup` precarga E5 (~24s) + LLMs, así la primera petición de chat no paga
ese coste. Es best-effort: si falta `NVIDIA_API_KEY` no tumba la API read-only.

## Notas para el frontend

- **SSE por POST:** `EventSource` NO sirve (es GET-only). Hay que usar `fetch()`
  con `response.body.getReader()` y parsear los frames `event:`/`data:` a mano.
- **Imágenes async:** `POST /api/images` → `job_id`; luego `GET` el `poll_url`
  hasta `status == "done"` y usar `image_url` (absoluta, servida en
  `/generated-visuals/...`).
- **Mock de imágenes:** `"mock": true` en el body (o `VISUAL_MOCK_ENABLED=true`)
  devuelve un SVG placeholder sin gastar Cloudflare.
- **CORS abierto** (`allow_origins=["*"]`), el frontend puede pegarle directo.
