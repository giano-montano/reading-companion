# Flujo E2E del producto — modelo mental y viaje de la información

**Fecha:** 2026-07-05 · **Autor:** Giano (con agente) · **Para:** validación humana

Este documento describe, en lenguaje llano, cómo viaja la información de punta a
punta en el MVP: qué manda el frontend, qué componente del backend lo recibe,
qué consulta, qué extrae, cómo lo parsea, qué atributos le agrega y a quién se lo
pasa — para cada funcionalidad. Es para que **entiendas y valides mi modelo
mental**. Donde marco 🔷 o ❓, necesito tu confirmación.

## Cómo leer esto (leyenda de estado)

- ✅ **Decidido y construido** — ya existe en el repo, validado esta sesión.
- 🟡 **Decidido, sin construir** — acordado en el diseño, falta código.
- 🔷 **Inferencia mía — validar** — mi modelo mental; puede estar mal.
- ❓ **Sin decidir** — decisión abierta que te toca a ti.

---

## 1. El modelo MVP: sin sesión, todo vive y muere en el navegador

🟡 No hay usuario persistente, ni base de datos de sesión, ni login. **Todo el
estado de una sesión de lectura vive en el navegador** (memoria de la pestaña):

- El texto canónico de la obra (se descarga una vez).
- El historial del chat (turnos alumno/compañero).
- El estado de lectura (A/B/C, ver §3).
- Flags de conversación: `pending_question`, `clarify_count`.

Si el alumno recarga la pestaña, se pierde todo. El **backend es sin estado
(stateless)**: cada request trae consigo TODO lo que necesita para responder.
No hay memoria de servidor entre turnos. Esto es una decisión de MVP, no una
limitación permanente.

Consecuencia de diseño importante: como el estado de lectura y el historial los
mantiene el frontend, **cada request es autocontenido**. El backend recibe el
mensaje + el contexto completo, decide, ejecuta una tool, responde, y olvida.

---

## 2. Los datos precomputados que el backend prepara UNA vez

Antes de que ningún alumno lea, hay una fase de **preprocesamiento por obra**
(offline, CLI). Dos etapas: una **ya construida** (Chang) y otra **pendiente**.

**Etapa A — preprocesamiento del libro ✅ (existe: `companion.cli.preprocess`).**
Toma un EPUB (`data/source/<epub>`) y produce tres artefactos derivados:
- `data/master/<book_id>.master.json` — fuente de verdad editable (bloques + chunks).
- `data/outputs/readers/<book_id>.reader.json` — para el frontend.
- `data/outputs/retrievals/<book_id>.retrieval.jsonl` — para el RAG (preguntas
  hipotéticas por chunk).

El **texto canónico** aquí NO sale de un `.txt`: es `"\n\n".join(chunk.text)` en
orden de lectura (`corpus/canonical_text.py`). Los `char_start/char_end` de cada
chunk se calculan sobre ese string con `recompute_offsets()`. Detalle en el
handoff de preprocessing (`agent_log/2026-07-05-preprocessing-pipeline.md`).

> ⚠️ **Cambio de contrato respecto a mi diseño original.** El chunk lleva
> **`section_ids: list[int]`** (un chunk puede cruzar secciones), no
> `section: int`. Las secciones son **manuales** (`sectioner.apply_pauses()`);
> por defecto el master sale con `sections: []`. Y el anti-spoiler que definió
> Chang es **por `chunk_id`** (chunks con id < actual completos; el actual
> parcial), no por sección/progreso. Esto **choca con `ScopeResolver`** (los
> modos `seccion`/`hasta_aqui` asumen `section: int`). Hay que reconciliarlo
> antes de cablear el agente. Ver §8.

**Etapa B — indexación vectorial + precómputos ⬜ (NO existe todavía).**
`jobs/index_book.py`, `graph_job.py`, `ner_job.py` están **vacíos**. Nadie
embebe el `retrieval.jsonl` en **ChromaDB**, ni emite el **catálogo/manifiesto**
que consume el `ScopeResolver`, ni `graph.json`, ni el store de NER. Esto es lo
que falta para que QA-RAG, RESUMIR, GRAFO y NER funcionen en runtime.

Resultado hoy: por cada obra existen **master + reader + retrieval.jsonl** (✅).
Faltan **Chroma + catálogo + graph.json + NER** (⬜).

---

## 3. Modelo mental del frontend 🔷 (esto quiero que valides)

Mi imagen del frontend hoy. **No lo he construido; esto es inferencia.**

Al abrir una obra, el frontend descarga: **(a)** el texto canónico y **(b)** el
catálogo de chunks (`chunk_id, section, char_start, char_end`). Con esos dos
ingredientes el frontend puede hacer todo su trabajo local:

- **Renderiza** el texto canónico tal cual (contrato #1: el mismo string que usó
  el chunker; ni una normalización más).
- **Mapea scroll → offset → chunk → sección** usando el catálogo. De ahí salen
  las tres variables del estado de lectura, **calculadas en el cliente**:
  - **A) Foco:** qué `chunk_id`s intersectan el viewport ahora mismo.
  - **B) Última sección completada:** la sección justo antes del foco.
  - **C) Progreso máximo:** `max(C, sección_actual)` — solo sube, nunca baja.
- **Resalta citas:** cuando una respuesta trae `citations` (chunk_id + offsets),
  el frontend pinta esos rangos sobre el texto que ya está en pantalla.
- **Panel NER y barra de progreso:** son vistas locales (eventos del frontend),
  **no pasan por el LLM** (contrato #4).

El chat es una columna aparte. El historial y los flags viven en memoria de la
pestaña.

❓ **Cosas del frontend sin decidir que me afectan:**
- ¿El frontend descarga el catálogo completo, o el backend expone un endpoint
  para resolver scope y el frontend solo manda el rango del viewport? (Yo asumo
  que el frontend tiene el catálogo para calcular A/B/C sin ir al backend.)
- ¿Qué es "una sección" visualmente? (capítulo, escena, bloque). Lo define el
  chunker de Chang, pero el frontend necesita saberlo para la barra de progreso.

---

## 4. El sobre de cada request/response 🔷🟡

**Request** (frontend → API, en cada turno). Mi propuesta de forma:

```jsonc
{
  "book_id": "...",                     // qué obra
  "student_text": "¿por qué huye?",     // el mensaje del chat
  "history": [ {"role":"user","content":"..."}, ... ],
  "reading_state": {                    // calculado en el cliente (§3)
    "focus_chunk_ids": ["c-0007","c-0008"],
    "last_completed_section": 3,
    "max_progress_section": 4
  },
  "pending_question": false,            // ¿hay pregunta de comprensión abierta?
  "pending_question_text": null,        // el enunciado, si lo hay
  "clarify_count": 0,                   // presupuesto de repregunta del router
  "viewport": { "range_start": 4120, "range_end": 5200 }  // para RESUMIR/IMAGEN
}
```

**Response** (API → frontend) = un `ToolOutput` (o variante) serializado:
`{ tool, ok, message, citations, ...campos propios de la tool }`. El frontend
pinta `message` en el chat y resalta `citations` en el texto.

🟡 **Nadie ha construido el sobre ni la API todavía.** Es lo que sigue. El
Router, el ScopeResolver y los contratos de tools ya existen; falta el
**orquestador** que arme el sobre → llame al Router → resuelva scope/retrieval →
ejecute la tool → devuelva el `ToolOutput`.

---

## 5. El viaje genérico de un turno 🟡

Antes de ir tool por tool, el esqueleto común:

```
[Frontend] arma el sobre (§4) y hace POST /chat
     │
     ▼
[API / Orquestador]  (api/server.py — ⬜ por construir)
     │  1. Router.decide(student_text, pending_question, history, clarify_count)  ✅
     │        → RouterDecision {action, tool, query/answer, ...}
     │
     ├─ action == CLARIFY → responde la repregunta al alumno, FIN del turno
     │
     └─ action == ROUTE → 2. RESOLVER EL SCOPE de la tool elegida:
              · RESUMIR/IMAGEN → ScopeResolver (modo lo_que_veo, viewport)   ✅
              · QA-RAG         → Retriever (embed→top-k) gated a ≤ C         ✅(base)
              · EVALUACIÓN     → chunks de la sección de la pregunta (≤ C)   ✅
              · GRAFO          → graph.json filtrado por C                    ⬜
         3. ARMAR el ToolInput (scope + reading_state + args del router)
         4. EJECUTAR la tool → llama al content LLM (70B) si aplica          ⬜
         5. Devolver el ToolOutput
     ▼
[Frontend] pinta message en el chat + resalta citations en el texto
```

Punto clave que se repite: **el gate anti-spoiler (≤ C = `max_progress_section`)
se aplica en el paso 2, aguas arriba de la tool.** Cuando la tool corre, su
scope ya es seguro. La tool nunca reconsulta el vector store.

---

## 6. E2E por funcionalidad

### 6.1 QA-RAG — preguntar sobre la obra 🟡 (prioridad)

> El alumno escribe una pregunta libre: *"¿Por qué la aldea está vacía?"*

1. **Frontend** manda el sobre (§4) con `student_text` = la pregunta.
2. **Router** ✅ clasifica → `QA-RAG` (o cae aquí por defecto). Devuelve
   `RouterDecision{tool:"qa_rag", query:"¿Por qué la aldea está vacía?"}`.
3. **Orquestador** ⬜ toma `query` y llama al **Retriever** ✅: el **Embedder**
   ✅ vectoriza la pregunta → **ChromaDB** ✅ devuelve top-k `RetrievedDoc`
   (texto + offsets + score).
4. **Gate anti-spoiler** 🔷: se filtran los `RetrievedDoc` a
   `section <= max_progress_section` (C). ❓ *Quién filtra: el retriever con un
   metadata-filter de Chroma por `section`, o el orquestador podando después.*
   (Tarea de Chang; anotado en el handoff.)
5. Los `RetrievedDoc` supervivientes se parsean a `ScopeChunk` (chunk_id,
   offsets, text, **score** poblado) y se arma `QaRagInput{query, scope,
   reading_state}`.
6. **Tool qa_rag** ⬜ construye un prompt con la pregunta + los chunks como
   contexto, llama al **content LLM 70B** ✅(factory roto), y produce
   `QaRagOutput{message, answered, citations}`. `citations` = los chunks que
   realmente usó. Si nada relevante sobrevive el gate → `answered=false` y un
   mensaje honesto ("eso todavía no aparece en lo que has leído").
7. **Frontend** pinta la respuesta y resalta las `citations`.

### 6.2 EVALUACIÓN — participación en pregunta de comprensión 🟡 (prioridad)

> Postura de **participación, no corrección**. Distingue intento genuino de
> no-intento. Nunca da spoilers.

Este flujo tiene **dos momentos**:

**(a) Se plantea la pregunta.** 🔷❓ *Sin decidir dónde nace la pregunta:* la
genera el content LLM sobre la sección recién completada (B), o viene
precomputada. Cuando se muestra, el frontend guarda `pending_question=true` +
`pending_question_text` en memoria de la pestaña.

**(b) El alumno responde.** Su siguiente mensaje del chat es la respuesta.
1. **Frontend** manda el sobre con `pending_question=true`,
   `pending_question_text` = el enunciado, `student_text` = la respuesta.
2. **Router** ✅ ve `pending_question=true` y enruta directo a **EVALUACIÓN**
   *sin llamar al LLM clasificador* → `RouterDecision{tool:"evaluacion",
   answer:<respuesta del alumno>}`.
3. **Orquestador** ⬜ resuelve el scope de referencia: los chunks de la sección
   a la que pertenece la pregunta, que por construcción son ≤ C (**ScopeResolver
   modo `seccion` o `hasta_aqui`** ✅). Arma `EvaluateInput{question:<enunciado>,
   answer:<respuesta>, scope, reading_state}`.
4. **Tool evaluacion** ⬜ llama al **content LLM 70B** con postura de
   participación: ¿hubo intento genuino? Devuelve `EvaluateOutput{message:
   <retroalimentación que invita a seguir>, attempt_detected, citations}`. **No
   hay nota.**
5. **Frontend** limpia `pending_question` y pinta el mensaje.

### 6.3 IMÁGENES — apoyo visual del pasaje ❓ (prioridad, SIN DISEÑAR)

> **Esto no tiene contrato ni etiqueta en el router todavía.** Lo modelo para
> conversarlo; nada aquí está decidido.

Mi mejor conjetura del flujo:
1. **Frontend** manda el sobre; el alumno pide *"muéstrame cómo se ve esta
   escena"*. `viewport` acota el pasaje.
2. **Router** ❓ necesitaría una **5ª etiqueta `IMAGEN`** (hoy solo clasifica
   RESUMIR/QA-RAG/GRAFO). **Esto es un cambio de contrato del router** que hay
   que decidir.
3. **ScopeResolver modo `lo_que_veo`** ✅ selecciona los chunks del viewport
   (nunca más allá de C, anti-spoiler visual).
4. **Tool imagen** ❓ — aquí está el grueso de lo indeciso:
   - ¿La imagen se **genera** con un modelo texto→imagen, se **recupera** de un
     banco curado, o son **diagramas/esquemas**?
   - Si se genera: ¿qué modelo? Latencia (segundos), costo, y sobre todo
     **seguridad para menores** (filtro de contenido) — no es trivial.
   - El prompt de imagen se construiría a partir del texto del pasaje (resumido
     por el 70B a una descripción visual), respetando el anti-spoiler.
   - La salida `ToolOutput` necesitaría un campo nuevo (una URL o un blob de
     imagen), que **hoy no existe** en `contracts.py`.

❓ **Necesito que definas qué es "imágenes" antes de que yo diseñe su contrato.**
Es el mayor hueco de este documento.

### 6.4 RESUMIR — recapitular lo que se ve 🟡

1. **Frontend** manda el sobre con `viewport` (el rango visible).
2. **Router** ✅ → `RESUMIR` (sin args extra).
3. **ScopeResolver modo `lo_que_veo`** ✅ con `range_start/range_end` del
   viewport → `list[ScopeChunk]` (texto rebanado del canónico). 🔷 *Asumo
   viewport; también podría ser "resume la sección actual" (modo `seccion`).*
4. **Tool resumir** ⬜ → content LLM 70B → `SummarizeOutput{message, citations}`.
5. **Frontend** pinta el resumen y resalta los chunks resumidos.

### 6.5 GRAFO — mapa de personajes 🟡

1. **Frontend** → **Router** ✅ → `GRAFO`.
2. **Tool grafo** ⬜ lee `graph.json` (⬜ lo produce `graph_job`) y **filtra por
   C**: oculta nodos/aristas cuya `first_section > max_progress_section`. Devuelve
   `GraphOutput{nodes, edges, truncated_by_progress, ...}`. **No pasa por el
   content LLM** (es consulta a datos precomputados).
3. **Vista completa (spoilers):** requiere `confirmed=true`. Si el alumno la pide
   sin confirmar, la tool responde la vista segura + `requires_confirmation=true`
   y el frontend muestra un "¿seguro que quieres ver spoilers?".
4. **Frontend** renderiza el grafo (no es texto de chat; es un panel visual).

---

## 7. Qué existe vs. qué falta (recap honesto)

| Componente | Estado |
|---|---|
| Contratos de tools (`contracts.py`) | ✅ |
| Router 8B (`router.py`) | ✅ |
| ScopeResolver 4 modos (`resolver.py`) | ✅ |
| Retriever + Embedder + ChromaDB (base RAG) | ✅ (Chang extiende el gate) |
| `NarrativeChunker` (+ `section` en chunks) | ⬜ Chang |
| Job `index_book` + catálogo/manifiesto | ⬜ |
| Las 4 tools (ejecución + content LLM) | ⬜ |
| `graph_job` / `graph.json` | ⬜ |
| Orquestador + API FastAPI (el sobre) | ⬜ |
| `get_content_llm()` / `get_router_llm()` | ⚠️ factory roto (ver handoff §6) |
| Frontend | ⬜ (tecnología no-Python) |
| **Imágenes (contrato, router, tool)** | ❓ sin diseñar |

---

## 8. Preguntas abiertas que te toca decidir

1. **Imágenes**: ¿generadas / recuperadas / diagramas? ¿Qué modelo? ¿Filtro de
   seguridad para menores? → bloquea diseñar su contrato y la 5ª etiqueta del
   router. *(§6.3)*
2. **Catálogo al frontend**: ¿el frontend descarga el catálogo de chunks para
   calcular A/B/C localmente (mi supuesto), o pide scope al backend? *(§3)*
3. **De dónde nace la pregunta de EVALUACIÓN**: ¿la genera el 70B sobre la
   sección B, o precomputada? *(§6.2a)*
4. **Quién aplica el gate anti-spoiler en QA-RAG**: retriever (metadata-filter de
   Chroma por `section`) vs. orquestador. *(§6.1, tarea de Chang)*
5. **RESUMIR**: ¿resume el viewport (`lo_que_veo`) o la sección actual
   (`seccion`)? *(§6.4)*

---

*Documento vivo. Si algo marcado 🔷 se valida o algo ❓ se decide, actualízalo y
promuévelo a ✅/🟡.*
