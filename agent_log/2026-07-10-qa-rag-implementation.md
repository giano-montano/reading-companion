# Handoff — implementación de la tool QA-RAG

**Fecha:** 2026-07-10
**Autor:** agente de Rodri
**Estado:** vivo — quedan 3 libros por regenerar preguntas

## Resumen ejecutivo

Se implementó el pipeline QA-RAG completo: embedding → retrieval → anti-spoiler →
content LLM. Probado end-to-end con router 8B (~2s/query).

**Modelos:**
- **Embeddings:** `intfloat/multilingual-e5-base` (768d, local, mean pooling >512 tokens)
- **Router (clasificador):** `meta/llama-3.1-8b-instruct` (NVIDIA NIM, temp 0)
- **Content (respuestas):** `meta/llama-3.3-70b-instruct` (NVIDIA NIM, temp 0.2)

**Cambios principales:**
- `contracts.py`: + `max_progress_chunk_index` (anti-spoiler), + `history` (chat)
- `state.py`: `AgentState` con historial, clarify_count, pending_question
- `orchestrator.py`: pipeline embed → retrieve → anti-spoiler → tool
- `qa_rag.py`: prompt + content LLM → `QaRagOutput`
- `sentence_transformer.py`: migrado a E5-base con mean pooling y prefijos query/passage
- Scripts CLI: `insert_hypotheticals.py`, `index_to_chroma.py`, `benchmark_qa.py`

**Pendiente:** regenerar preguntas hipotéticas de 3 libros con la estrategia
"calidad > cantidad" (2-4 preguntas por chunk, sin relleno). Prompt en §1.

---

## Qué se construyó

Implementación completa del pipeline QA-RAG: desde la pregunta del alumno hasta la
respuesta del LLM, pasando por embedding, retrieval en ChromaDB, gate anti-spoiler
y generación con el content LLM.

### Archivos nuevos / modificados

```
src/companion/agent/
├── state.py              ← NUEVO  AgentState (historial, clarify_count, pending_question)
├── orchestrator.py       ← NUEVO  QaRagOrchestrator (pipeline completo)
├── router.py             ← EDIT   lint fix (Field unused)
└── tools/
    ├── contracts.py       ← EDIT   +history en QaRagInput, +max_progress_chunk_index en ReadingState
    └── qa_rag.py          ← NUEVO  QaRagTool (prompt + content LLM → QaRagOutput)

src/companion/embedders/
└── sentence_transformer.py ← REWRITE  E5-base (768d), mean pooling para >512 tokens,
                               prefijos query: / passage: (convención E5)

src/preprocesamiento/
├── insert_hypotheticals.py ← NUEVO  Inserta preguntas en retrieval.jsonl
├── index_to_chroma.py      ← NUEVO  Indexa retrieval.jsonl en ChromaDB
└── benchmark_qa.py          ← NUEVO  10 preguntas, mide latencia y hit rate

.env                        ← EDIT   EMBEDDING_MODEL=intfloat/multilingual-e5-base
data/outputs/hypotheticals/ ← NUEVO  Preguntas hipotéticas por libro (formato diverso)
```

### Modelos utilizados

| Rol | Modelo | Provider | Detalles |
|---|---|---|---|
| **Embeddings** | `intfloat/multilingual-e5-base` | local (sentence-transformers) | 768 dims, max_seq=512, mean pooling, prefijos `query:`/`passage:` |
| **Router (clasificador)** | `meta/llama-3.1-8b-instruct` | NVIDIA NIM | temp 0, clasifica intención: resumir / qa_rag / grafo |
| **Content (respuestas)** | `meta/llama-3.3-70b-instruct` | NVIDIA NIM | temp 0.2, genera respuestas QA-RAG |
| **Embeddings (anterior)** | `paraphrase-multilingual-MiniLM-L12-v2` | local | 384 dims, max_seq=128 — **descartado** (truncaba 75% del chunk) |

**Nota sobre latencia:** el 70B tarda ~30s/query. Para desarrollo y benchmarks
se usó el router 8B (~2s/query). En producción conviene evaluar
`deepseek-ai/deepseek-v4-flash` como punto medio.

### Cambios detallados por archivo

**Nuevos:**
| Archivo | Descripción |
|---|---|
| `src/companion/agent/state.py` | `AgentState`: historial (últimos 5 pares user/assistant), `clarify_count`, `pending_question`, `pending_question_text`. Métodos `trim_history()` y `add_turn()`. |
| `src/companion/agent/orchestrator.py` | `QaRagOrchestrator`: pipeline completo. Constructor recibe `Embedder`, `VectorStore`, `LLMProvider`, `top_k`. Método `run(query, agent_state, book_id, reading_state) → QaRagOutput`. |
| `src/companion/agent/tools/qa_rag.py` | `QaRagTool`: construye prompt (system + chunks + historial + query), llama al content LLM, parsea y devuelve `QaRagOutput`. Si no hay chunks → `answered=False`. |
| `src/preprocesamiento/insert_hypotheticals.py` | CLI: lee `hypotheticals.jsonl`, actualiza `metadata.hypothetical_questions` en `retrieval.jsonl`. Flags: `--all`, `--book_id`, `--dry-run`, `--list`. |
| `src/preprocesamiento/index_to_chroma.py` | CLI: indexa `retrieval.jsonl` → ChromaDB. Construye `embedded_text = preguntas + "\n\n" + texto`. Colecciones: `rag_{book_id}`. |
| `src/preprocesamiento/benchmark_qa.py` | 10 preguntas de prueba sobre 4 libros. Mide latencia (embedding + retrieval + LLM) y hit rate. |
| `data/outputs/hypotheticals/` | 8 archivos `.hypotheticals.jsonl`, uno por libro, con preguntas hipotéticas por chunk. |
| `agent_log/2026-07-10-qa-rag-implementation.md` | Este handoff. |

**Modificados:**
| Archivo | Cambio |
|---|---|
| `src/companion/agent/tools/contracts.py` | `ReadingState` + `max_progress_chunk_index: int` (gate anti-spoiler por chunk). `QaRagInput` + `history: list[dict]`. |
| `src/companion/embedders/sentence_transformer.py` | Cambio de modelo a `intfloat/multilingual-e5-base` (768d). Prefijos E5 (`query:` / `passage:`). Mean pooling para chunks >512 tokens. |
| `src/companion/agent/router.py` | Lint fix: removido `Field` no usado. |
| `.env` | `EMBEDDING_MODEL=intfloat/multilingual-e5-base` |

### Modelo de embeddings

Se cambió de `paraphrase-multilingual-MiniLM-L12-v2` (384d, max_seq_length=128) a
`intfloat/multilingual-e5-base` (768d, max_seq_length=512) con dos mejoras críticas:

1. **Prefijos E5:** `query: ` para consultas, `passage: ` para chunks. Sin estos
   prefijos el modelo rinde mucho peor. Están implementados en el embedder.

2. **Mean pooling** para chunks >512 tokens: se parten en segmentos solapados (25%
   overlap), se embebe cada uno, y se promedian los vectores. Resultado: **0%
   truncación**, ningún chunk pierde contenido.

### Flujo QA-RAG (probado end-to-end con router 8B)

```python
orchestrator = QaRagOrchestrator(embedder, vector_store, llm)
result = orchestrator.run(
    query="¿Por qué los padres del muchacho no lo dejaban pescar?",
    agent_state=AgentState(history=[...]),
    book_id="el_viejo_y_el_mar_ernest_hemingway",
    reading_state=ReadingState(max_progress_chunk_index=20),
)
# → QaRagOutput(message="...", citations=[...], answered=True)
```

Pipeline interno:
1. `embedder.embed("query: " + query)` → vector
2. `chroma.search(vector, variant=book_id, top_k)` → RetrievedDoc[]
3. Anti-spoiler: filtrar `chunk_index <= max_progress_chunk_index`
4. RetrievedDoc → ScopeChunk (con char_start, char_end, score)
5. `QaRagTool.execute(QaRagInput(query, scope, history, reading_state))`
   - Construye prompt: system + contexto (chunks numerados) + historial + pregunta
   - `content_llm.chat(messages)` → respuesta
   - `QaRagOutput(message, citations, answered, ok)`

### Anti-spoiler

Usa `max_progress_chunk_index` (nuevo campo en `ReadingState`). El índice numérico
se extrae del chunk_id: `int(chunk_id.rsplit("::", 1)[-1])`. Solo se permiten chunks
con índice ≤ max_progress. Si `max_progress_chunk_index == 0`, se desactiva el gate
(inicio del libro).

### Latencia (benchmark con router 8B, 10 preguntas)

| Métrica | Valor |
|---|---|
| Setup embedder (one-time) | ~24s |
| Latencia media por query | 1.8s |
| Latencia min/max | 0.8s / 3.4s |
| Respondidas | 10/10 |
| Hits en top-3 | 2/10 |

**Nota:** El content LLM 70B (NVIDIA) es mucho más lento (~30s/query) pero da mejor
calidad. Para desarrollo se usó el router 8B.

---

## Tareas pendientes para completar la tool

### 1. Regenerar preguntas hipotéticas de 3 libros ⬜

**Estado actual de `data/outputs/hypotheticals/`:**

| Libro | Chunks | Formato | Estado |
|---|---|---|---|
| el_viejo_y_el_mar | 139 | 5 tipos (forzado) ⚠️ | Revisar |
| la_metamorfosis | 96 | 5 tipos (forzado) ⚠️ | Revisar |
| cronica_de_una_muerte_anunciada | 137 | 5 tipos (forzado) ⚠️ | Revisar |
| el_maravilloso_mago_de_oz | 156 | 5 tipos (forzado) ⚠️ | Revisar |
| matalache | 354 | 5 tipos (forzado) ⚠️ | Revisar |
| **las_aventuras_de_tom_sawyer** | 382 | 3 preguntas viejas ❌ | **Regenerar** |
| **viaje_al_centro_de_la_tierra** | 414 | ❌ no existe | **Regenerar** |
| **la_ciudad_y_los_perros** | 675 | incompleto (135/675) | **Regenerar** |

Los 5 libros con ⚠️ tienen preguntas generadas con el formato viejo de 5 tipos
forzados (pueden tener relleno). Idealmente regenerarlos también con la nueva
estrategia, pero **la prioridad son los 3 pendientes**.

#### Estrategia de generación: calidad > cantidad

**NO generar 5 preguntas por chunk.** Eso produce relleno que diluye el
embedding. En vez de eso, aplicar estas reglas:

1. **Solo generar pregunta si el chunk tiene contenido sustancial para ella.**
   Si un chunk es puramente transicional ("caminaron hasta la casa"), no
   fuerces una pregunta. Mejor 2 preguntas certeras que 5 de relleno.

2. **Cada pregunta debe usar vocabulario de estudiante para conceptos del
   texto.** El objetivo es tender un puente entre cómo pregunta un alumno
   ("¿cómo es físicamente?") y cómo lo dice el texto ("era flaco y
   desgarbado, con arrugas profundas...").

3. **Tipos de pregunta a cubrir, POR ORDEN DE PRIORIDAD:**
   - **Descriptiva** — si el chunk presenta un personaje, lugar u objeto nuevo
   - **Causa/consecuencia** — si hay un evento con motivación clara
   - **Emoción/relación** — si hay expresión emocional o interacción entre personajes
   - **Conflicto/decisión** — si hay un dilema o elección
   - **Significado** — si hay una frase simbólica o expresión inusual
   - **Factual** — solo si la información está aislada y es relevante
     (evitar preguntas obvias tipo "¿quién dijo X?")

4. **Rango: 2-4 preguntas por chunk.** Si el chunk es rico (introduce personaje,
   tiene evento con causa, muestra emoción), dar 4. Si es pobre, dar 2. Si es
   puramente transicional, dar 2 breves o incluso 0 (escribir `[]`).

5. **NUNCA inventar.** Si el chunk no menciona el rostro de un personaje, no
   preguntar "¿cómo es su rostro?". Si no hay conflicto, no inventar un dilema.

6. **Las preguntas deben matchear queries reales de estudiantes.** Pensar:
   "si un alumno de 14 años leyera este fragmento, ¿qué me preguntaría?"

#### Cómo generar las preguntas

Las preguntas NO las genera el content LLM del proyecto (70B) ni el embedder. Las
genera un agente de terminal (Claude, ChatGPT, etc.) usando el siguiente prompt.

**Prompt para el agente:**

```
Eres un experto en comprensión lectora para sistemas RAG educativos.

Vas a recibir un archivo JSONL con chunks narrativos. Cada línea:
  {"chunk_id": "libro::chunk::N", "text": "..."}

Para CADA chunk, genera entre 2 y 4 preguntas hipotéticas en español.
NO generes 5 por obligación: calidad > cantidad.

Estrategia:
- SOLO genera una pregunta si el chunk tiene contenido real para ella.
  Si es un fragmento puramente transicional, genera 2 breves o incluso 0.
- Cada pregunta debe usar vocabulario de estudiante para conceptos del texto.
  Ej: el texto dice "era flaco y desgarbado" → preguntar "¿cómo es físicamente?"

Tipos de pregunta por orden de prioridad:
1. DESCRIPTIVA: ¿Cómo es X? ¿Qué aspecto tiene? — si el chunk presenta un
   personaje, lugar u objeto nuevo
2. CAUSA/CONSECUENCIA: ¿Por qué X? ¿Qué provocó Y? — si hay evento con motivo
3. EMOCIÓN/RELACIÓN: ¿Cómo se siente X? ¿Qué relación hay entre X e Y? —
   si hay expresión emocional o interacción
4. CONFLICTO/DECISIÓN: ¿Qué dilema enfrenta? ¿Qué decide hacer? —
   si hay tensión o elección
5. SIGNIFICADO: ¿Qué significa la frase "..."? — si hay expresión simbólica
6. FACTUAL: solo si la información es relevante y no obvia

Reglas:
- Preguntas breves (10-25 palabras), naturales, como un alumno de 14 años
- NO inventar contenido que no esté en el chunk
- NO hacer spoilers
- Rango: 2-4 preguntas. Si el chunk es pobre, 2. Si es rico, 4.
  Si es puramente transicional, puede ser 1 o incluso 0.

Escribe la salida en este archivo (SOBRESCRIBIR):
  data/outputs/hypotheticals/<book_id>.hypotheticals.jsonl

Formato JSONL (sin comas entre líneas):
{"chunk_id": "libro::chunk::1", "hypothetical_questions": ["preg1", "preg2"]}
{"chunk_id": "libro::chunk::2", "hypothetical_questions": ["preg1", "preg2", "preg3"]}

Trabaja en tandas de 50-70 chunks. Lee del archivo de retrieval, genera
preguntas, escribe al de salida ANTES de la siguiente tanda.
```

**Archivos de entrada (retrieval) para cada libro pendiente:**
```
data/outputs/retrieval/las_aventuras_de_tom_sawyer_mark_twain.retrieval.jsonl
data/outputs/retrieval/viaje_al_centro_de_la_tierra_julio_verne.retrieval.jsonl
data/outputs/retrieval/la_ciudad_y_los_perros_mario_vargas_llosa.retrieval.jsonl
```

**Archivos de salida (sobrescribir):**
```
data/outputs/hypotheticals/las_aventuras_de_tom_sawyer_mark_twain.hypotheticals.jsonl
data/outputs/hypotheticals/viaje_al_centro_de_la_tierra_julio_verne.hypotheticals.jsonl
data/outputs/hypotheticals/la_ciudad_y_los_perros_mario_vargas_llosa.hypotheticals.jsonl
```

### 2. Insertar preguntas en retrieval.jsonl ⬜

Una vez regenerados los 8 libros:

```bash
.venv/Scripts/python.exe -m preprocesamiento.insert_hypotheticals --all
```

Esto lee cada `hypotheticals.jsonl` y actualiza el campo
`metadata.hypothetical_questions` en el `retrieval.jsonl` correspondiente.

Flags útiles: `--dry-run`, `--book_id <id>`, `--list`.

### 3. Reindexar ChromaDB ⬜

```bash
.venv/Scripts/python.exe -m preprocesamiento.index_to_chroma --all --clear
```

Esto:
1. Borra las colecciones existentes
2. Lee cada `retrieval.jsonl`
3. Construye `embedded_text = preguntas + "\n\n" + texto`
4. Embebe con E5-base (`passage:` prefix, mean pooling si >512 tokens)
5. Almacena en `chroma_db/` (8 colecciones: `rag_{book_id}`)

Flags: `--book_id`, `--all`, `--dry-run`, `--list`, `--clear`.

**Tiempo estimado:** ~15-20 minutos en CPU (E5 es más lento que MiniLM, ~10s por
lote de 32 chunks).

### 4. Ajustar el prompt de QA-RAG ⬜

El prompt actual en `src/companion/agent/tools/qa_rag.py` es funcional pero
genérico. Hay que darle:
- Tono educativo para secundaria
- Instrucciones más específicas sobre citas y formato
- Manejo de casos borde (preguntas off-topic, sin contexto suficiente)

### 5. Exponer endpoint HTTP (cuando se necesite frontend) ⬜

El `QaRagOrchestrator` es standalone. Para integrarlo con el frontend, crear
un endpoint en FastAPI (`POST /chat`) que:
1. Reciba `{query, history, book_id, reading_state}`
2. Construya `AgentState` y `ReadingState`
3. Ejecute `orchestrator.run()`
4. Devuelva `QaRagOutput` serializado

### 6. Benchmark final ⬜

```bash
.venv/Scripts/python.exe -m preprocesamiento.benchmark_qa
```

Comparar hit rate antes/después de las nuevas preguntas. Objetivo: >50% hits
en top-5 (vs 20% actual en top-3).

---

## Contratos modificados (superficie compartida)

**`contracts.py`** — cambios que afectan a Giano y Chang:

```python
# ReadingState: nuevo campo
max_progress_chunk_index: int = Field(0)  # gate anti-spoiler por chunk

# QaRagInput: nuevo campo
history: list[dict[str, str]] = Field(default_factory=list)  # historial de chat
```

**`sentence_transformer.py`** — cambio de modelo:
- Antes: `paraphrase-multilingual-MiniLM-L12-v2` (384d, max_seq=128)
- Ahora: `intfloat/multilingual-e5-base` (768d, max_seq=512, mean pooling)
- `.env`: `EMBEDDING_MODEL=intfloat/multilingual-e5-base`

---

## Cómo probar rápidamente

```bash
# Verificar que la DB tiene los 8 libros
.venv/Scripts/python.exe -m preprocesamiento.index_to_chroma --list

# Probar una query con mock (sin llamar a NVIDIA)
.venv/Scripts/python.exe -c "
from companion.agent.orchestrator import QaRagOrchestrator
from companion.agent.state import AgentState
from companion.agent.tools.contracts import ReadingState
from companion.embedders.factory import get_embedder
from companion.vector_store.chroma_store import ChromaVectorStore
from companion.providers.mock_llm import MockLLMProvider
from companion.config import settings

orch = QaRagOrchestrator(get_embedder(),
    ChromaVectorStore(persist_dir=settings.chroma_persist_dir),
    MockLLMProvider())

r = orch.run('¿Quién es Santiago?', AgentState(),
    'el_viejo_y_el_mar_ernest_hemingway',
    ReadingState(max_progress_chunk_index=10))
print(r.message)
"

# Benchmark completo (usa router 8B, necesita NVIDIA_API_KEY)
.venv/Scripts/python.exe -m preprocesamiento.benchmark_qa
```

---

## Decisiones abiertas

- ¿Content LLM final? El 70B (NVIDIA) es lento (~30s) pero preciso. El 8B es
  rápido (~2s) pero menos profundo. deepseek-v4-flash podría ser el punto medio.
- ¿top_k óptimo? Actualmente 3 en config. Subir a 5-7 mejoraría hit rate.
- ¿Cross-encoder reranker? Podría duplicar el hit rate con ~100ms extra.
- ¿Las preguntas hipotéticas van en el embedded_text o solo en metadata? Actualmente
  van en embedded_text (preguntas + "\n\n" + texto). La evidencia del benchmark
  sugiere que diluyen la señal para ciertos tipos de queries. Evaluar con las
  nuevas preguntas de 5 tipos antes de decidir.
