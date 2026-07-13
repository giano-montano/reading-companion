# Handoff — Contratos de tools, ScopeResolver y Router

**Fecha:** 2026-07-05
**Autor:** Giano (con agente de terminal)
**Para:** Chang (QA-RAG, chunking) + su agente de terminal
**Rama:** `dev`

Este documento es la fuente de verdad de lo construido en esta sesión. Está
escrito para que tu agente lo lea entero antes de tocar código y sepa dónde
enchufar tu avance sin romper contratos. Si cambias un contrato, **actualiza
este archivo en el mismo commit**.

---

## 0. TL;DR para tu agente

Se implementaron **tres piezas**, todas por encima de la infraestructura RAG ya
migrada de F1:

| Pieza | Archivo | Estado |
|---|---|---|
| Contratos de I/O de las 4 tools | `src/companion/agent/tools/contracts.py` | ✅ completo, validado |
| ScopeResolver (4 modos) | `src/companion/scope/resolver.py` | ✅ completo, validado |
| Router (8B, clasificación) | `src/companion/agent/router.py` | ✅ completo, validado con LLM falso |

**Nada de esto ejecuta tools ni llama al content LLM todavía.** Son la capa de
*decisión* y *selección*. La *ejecución* (las 4 tools, el orquestador, la API)
está por construir.

**Lo que te toca a ti (y dónde te conectas):** §5.

---

## 1. Los 4 contratos que no se rompen (recordatorio)

1. **Texto canónico.** Lo produce `build_canonical_text()` en
   `src/companion/corpus/canonical_text.py` (= `"\n\n".join(chunk.text)` en orden
   de lectura). *(Nota 2026-07-07: reemplazó a `TextLoader.load()`, ya
   eliminado, cuando Chang integró el pipeline de EPUB.)* Es EL MISMO string que
   renderiza el frontend. Una sola normalización. Si el chunker aplica otra, los
   offsets apuntan mal en silencio. `recompute_offsets()` los recalcula;
   `validate_offsets()` asegura `canonical[char_start:char_end] == chunk.text`.
2. **Offsets absolutos.** `Chunk.char_start` / `char_end` son offsets absolutos
   sobre ese string canónico. Se persisten en metadata de Chroma. Al leerlos:
   `int(meta.get("char_start", 0))`.
3. **Dos LLM, dos providers.** `get_router_llm()` (8B, temp 0) y
   `get_content_llm()` (70B) tienen tags de cache distintos. Nunca compartir
   instancia entre roles.
4. **El agente es fracción del producto.** El panel NER y el estado de lectura
   (scroll, progreso) son EVENTOS del frontend, no pasan por el LLM.

---

## 2. `contracts.py` — la frontera tipada de las tools

Define la forma de entrada/salida de las 4 tools. **Es el archivo que más te
afecta si cambias algo**, porque el resolver y el router importan de aquí.

### Tipos compartidos
- `ScopeChunk` — `chunk_id` + `char_start`/`char_end` + `text` + `score|None`.
  Invariante: `text == canonical_text[char_start:char_end]`. `score` solo lo
  pone el Retriever (QA-RAG); es `None` para todo lo demás.
- `ReadingState` — las 3 variables del frontend: `focus_chunk_ids` (A),
  `last_completed_section` (B), `max_progress_section` (C). **El LLM nunca las
  produce.** El filtro anti-spoiler usa **C**, nunca A.
- `Citation` — `chunk_id` + offsets, para resaltar la fuente en el frontend.

### Base
- `ToolInput` = `tool` + `scope: list[ScopeChunk]` + `reading_state`.
- `ToolOutput` = `tool` + `ok` + `message` (texto del chat) + `citations`.

### Variantes
| Tool | Input añade | Output añade |
|---|---|---|
| `resumir` | — | — |
| `qa_rag` | `query` | `answered: bool` |
| `evaluacion` | `question`, `answer` | `attempt_detected: bool` |
| `grafo` | `view: safe\|full`, `confirmed: bool` | `nodes`, `edges`, `truncated_by_progress`, `requires_confirmation` |

Más `ToolInputUnion` / `ToolOutputUnion` (discriminated unions por `tool`) para
el borde router/API.

### Decisión de diseño clave (te concierne)
**El gate anti-spoiler se aplica AGUAS ARRIBA**, en el ScopeResolver/Retriever,
NO dentro de la tool. Cuando el scope llega a una tool, ya es seguro. Las tools
confían en su scope y **nunca reconsultan el vector store**. Los campos de
salida `truncated_by_progress` / `answered` solo *reportan* el efecto.

> **⚠️ QA-RAG (tu tool):** tu retriever DEBE devolver solo chunks con
> `section <= max_progress_section` (C). O lo filtras tú en el retriever, o lo
> hace el orquestador antes de armar el `QaRagInput`. Define quién y déjalo
> escrito. Ver §5.

---

## 3. `resolver.py` — ScopeResolver (selección determinista)

Scoping **no es retrieval**: sin embedding, sin vector search, sin LLM. Es un
filtro puro sobre un catálogo de `ChunkRef`.

### API
- Constructor: `ScopeResolver(catalog: list[ChunkRef], canonical_text: str)`.
- `ChunkRef` = `chunk_id`, `section: int`, `char_start`, `char_end`, `chunk_index`.
- `resolve(ScopeRequest) -> list[ScopeChunk]`, o los 4 métodos directos:
  `visible(range_start, range_end)`, `section(section_id)`,
  `up_to(max_progress_section)`, `work()`.
- `ScopeRequest` valida por modo que lleguen los campos requeridos.

### Los 4 modos
| Modo | Filtro |
|---|---|
| `lo_que_veo` | intersección con `[range_start, range_end)` (semiabierto) |
| `seccion` | `section == section_id` |
| `hasta_aqui` | `section <= max_progress_section` (anti-spoiler, C) |
| `obra` | todos |

### Invariantes / decisiones
- **Hidratación de texto por rebanado del canónico**: `text =
  canonical[char_start:char_end]`. Único lugar que produce texto de scope →
  imposible desincronizar offsets. Por eso el constructor exige `canonical_text`.
- **Intervalos semiabiertos** `[start, end)` como `text[start:end]`. Un chunk
  intersecta el viewport si `char_start < range_end and char_end > range_start`.
- **Orden de lectura** garantizado: catálogo ordenado por
  `(char_start, chunk_index)`.
- El resolver **nunca calcula** el rango/sección; llegan del frontend.

---

## 4. `router.py` — Router (8B, decide, no ejecuta)

Decide QUÉ tool maneja el mensaje. **No ejecuta la tool, no resuelve scope.**

### API
- `Router(router_llm: LLMProvider, max_reprompts=2)`.
  El LLM se **inyecta** (debe ser `get_router_llm()`).
- `decide(student_text, pending_question, history=None, clarify_count=0)
  -> RouterDecision`.

### `RouterDecision`
`action` (`route` | `clarify`), `tool`, `query` (QA-RAG), `answer`
(EVALUACIÓN), `clarification`, `clarify_count`, `source`, `raw_label`.
`scope` y `reading_state` **ausentes a propósito**: los rellena el orquestador.

### Flujo
```
pregunta_pendiente == True ──► ROUTE EVALUACIÓN (answer=texto)  [0 llamadas LLM]
else → clasificar 8B (temp 0) entre {RESUMIR, QA-RAG, GRAFO, NO_CLASIFICABLE}
    tool real       ──► ROUTE esa tool  (QA-RAG lleva query=texto)
    NO_CLASIFICABLE ──► clarify_count<2 ? CLARIFY (repregunta) : ROUTE QA-RAG (default)
```
- **EVALUACIÓN no es objetivo del clasificador**: solo se alcanza por
  `pregunta_pendiente`.
- Ruta por defecto = **QA-RAG** (tu tool).
- Parseo de etiqueta robusto a salida ruidosa (match por contención, orden
  largo→corto: `QA-RAG` gana a `QA`).

---

## 5. DÓNDE ENCHUFAS TÚ (Chang)

### 5.1 Chunking → el `section` es un requisito NUEVO
`ChunkRef.section` y `ReadingState.max_progress_section` son **enteros ordenados
comparables**. Tu `NarrativeChunker` debe **asignar un índice de sección entero a
cada chunk** (en `Chunk.metadata`, p.ej. `metadata["section"]`). Sin eso, los
modos `seccion` / `hasta_aqui` y todo el anti-spoiler no funcionan.

- Decide qué es una "sección" (capítulo, escena, bloque de N párrafos) y déjalo
  documentado. El contrato solo exige que sea **monótona en orden de lectura**.
- `Chunk.chunk_id` hoy es un UUID. Hay un TODO en `schemas.py:30` sobre darle
  "conciencia de temporalidad" (1,2,3) para spoilers. Si migras a IDs
  ordinales, avisa: el router/resolver no dependen del formato del id, pero el
  frontend y las citations sí lo usan como clave.

### 5.2 El catálogo `list[ChunkRef]` — punto de cableado abierto
El ScopeResolver consume un catálogo, pero **nadie lo construye todavía**. Lo
natural: el job `index_book` (`src/companion/jobs/index_book.py`, hoy vacío)
emite un manifiesto ligero (JSON) con
`{chunk_id, section, char_start, char_end, chunk_index}` por chunk, derivado de
la metadata que persistes en Chroma. Ese manifiesto alimenta al resolver.
**Decidan juntos**: ¿manifiesto en disco vs. leer metadata de Chroma al vuelo?

### 5.3 QA-RAG y el gate anti-spoiler
Tu `Retriever` / tool `qa_rag` DEBE respetar `max_progress_section` (C). El
`ScopeChunk` que entra a `QaRagInput.scope` debe estar ya filtrado a
`section <= C`. Opciones:
- filtrar en el retriever (metadata filter de Chroma por `section`), o
- que el orquestador pode los `RetrievedDoc` antes de armar el input.
Elige una y escríbela aquí. `RetrievedDoc` (en `schemas.py`) ya trae offsets;
si le añades `section` a su metadata, el pod es trivial.

### 5.4 Si cambias contratos
- Editar `contracts.py` toca a: `resolver.py`, `router.py`, y (futuro)
  orquestador + API + frontend. Los offsets y `ReadingState` son los más
  sensibles.
- Mantén los nombres de campo o coordina el rename en un solo commit.
- Vuelve a correr las validaciones de §7.

---

## 6. Tensiones y cuestionamientos abiertos

Cosas que implementamos con una decisión tomada pero que **puedes cuestionar**:

1. **`ScopeChunk` incluye `text`** (rebanado del canónico), no solo id+offsets.
   Ventaja: las tools no releen Chroma; se respeta el contrato de una sola
   normalización. Riesgo: duplica texto en memoria para scopes grandes (modo
   `obra`). Alternativa: scope solo con offsets y que la tool hidrate. **Sin
   decidir para scopes muy grandes.**
2. **`clarify_count` es un parámetro extra del router**, además de las 3
   entradas "oficiales" (texto, pregunta_pendiente, historial). No cabía en el
   historial `{role,content}`. Su hogar natural es `AgentState`
   (`src/companion/agent/state.py`, hoy vacío). **Al construir el estado,
   muévelo ahí.**
3. **Gate anti-spoiler centralizado aguas arriba** (no en cada tool). Simple y
   con C como única compuerta, pero **exige disciplina**: cualquier ruta que
   arme un `scope` debe pasar por el gate. Fácil de olvidar en QA-RAG (§5.3).
4. **Sección como `int`**. `ScopeRequest.section_id` es `int`, no string. Si tu
   chunker produce ids de sección no numéricos (p.ej. `"cap-3.2"`), hay que
   cambiar el tipo en resolver + contracts. **Coordinar antes de implementar.**
5. **GRAFO no extrae `view` en el router**. Detectar "muéstrame TODO el grafo"
   → `full` (que requiere confirmación) se dejó a la tool/orquestador. Puede
   que quieras un mini-clasificador de sub-intención. **Sin decidir.**
6. **`get_router_llm()` / `get_content_llm()` están ROTOS**
   (`src/companion/providers/factory.py`): referencian un `provider` inexistente
   y tienen un error de sintaxis (indentación en línea 22). El router los evita
   inyectando el LLM. **Alguien debe arreglar el factory** antes del primer
   extremo-a-extremo real. No lo tocamos para no pisar decisiones de temperatura
   / params de `NvidiaLLMProvider`.

---

## 7. Cómo validar (reproducible)

No hay suite de tests aún (`tests/` no existe). Validamos con scripts ad-hoc y
un LLM falso. Para re-verificar:

```bash
# Windows: usar el intérprete del venv
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'src'); \
  import companion.agent.tools.contracts, companion.scope.resolver, \
         companion.agent.router; print('imports OK')"
```
El router se probó con un `LLMProvider` falso que devuelve etiquetas fijas
(pending→evaluación con 0 llamadas al LLM; cada etiqueta→su tool; ruido→qa_rag;
NO_CLASIFICABLE→clarify×2→fallback qa_rag). El resolver se probó con un catálogo
sintético de 5 chunks / 3 secciones (los 4 modos + fronteras semiabiertas +
`text == slice` + guards de validación).

> **Deuda:** convertir estos scripts en `tests/` con `pytest` (está en
> `[project.optional-dependencies].dev`). Buen primer PR conjunto.

---

## 8. Mapa de módulos (estado actual)

```
src/companion/
  schemas.py            ✅ Document, Chunk, EnrichedChunk, RetrievedDoc  (F1)
  config.py             ✅ router_model, content_model, etc.            (F1)
  corpus/text_loader.py ✅ normalización canónica                       (F1)
  providers/            ✅ LLM/NER providers  |  factory.py ROTO (§6.6)
  embedders/ vector_store/ retrieval/ enrichers/   ✅ RAG base          (F1)
  chunkers/base.py      ✅ ABC   | narrative.py  ⬜ TU TAREA
  scope/resolver.py     ✅ ESTA SESIÓN
  agent/router.py       ✅ ESTA SESIÓN
  agent/tools/contracts.py  ✅ ESTA SESIÓN
  agent/tools/{summarize,qa_rag,evaluate,graph}.py  ⬜ vacías
  agent/state.py        ⬜ vacía (aquí va clarify_count, §6.2)
  jobs/{index_book,ner_job,graph_job}.py  ⬜ vacías (catálogo, §5.2)
  api/server.py         ⬜ vacía
```
```
```
