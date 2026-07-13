# Handoff — EVALUACIÓN implementada + panel NER por chunk en el reader

**Fecha:** 2026-07-11
**Autor:** agente de Giano (backend)
**Para:** Erick (frontend) — responde su §3 de
[`2026-07-11-frontend-evaluacion-secciones.md`](2026-07-11-frontend-evaluacion-secciones.md) —
y Chang (dato nuevo en el reader + tarea pendiente suya al final).

## 1. EVALUACIÓN — ya funciona en `/api/chat`

Decidido con Giano+Chang (2026-07-11): **feedback formativo** (reconoce
aciertos, señala vacíos apoyándose en pasajes, invita a releer; sin nota,
sin "incorrecto" seco) y **scope por retrieval**: se embebe
`pregunta + respuesta` → top-k Chroma → gate anti-spoiler por
`max_progress_chunk_index`. Mismo pipeline que QA-RAG, otro system prompt.

### Flujo (lo que Erick ya cableó sigue válido tal cual)

1. Frontend manda `agent_state.pending_question = true` y
   `pending_question_text` = la pregunta del profe.
2. El router NO llama al 8B: fuerza `evaluacion` con `answer` = mensaje del
   alumno. La pregunta la toma el backend de `pending_question_text`.
3. Si `pending_question=true` pero `pending_question_text` viene vacío →
   `notice` pidiéndolo (no crashea, no evalúa).

### Eventos SSE (respuesta a Erick §3.3)

```
route      {tool: "evaluacion"}
token      {delta}                      ← igual que QA-RAG, pinta incremental
citations  {citations, answered, ok}    ← MISMA forma que QA-RAG: tu render actual sirve
evaluation {attempt_detected, ok}       ← NUEVO, terminal, antes de done
done       {}
```

`evaluation` es **aditivo**: si tu parser ignora eventos desconocidos, no
necesitas tocar nada hoy. Cuando quieras pintarlo (p. ej. badge "intento
válido"), ahí está. `attempt_detected` es una **heurística de participación**
(≥3 palabras en la respuesta), no un juicio de calidad — el juicio real va en
el texto del feedback.

### Respuestas al §3 de Erick

1. **¿Dónde viaja la pregunta del profe?** → Chang añadirá el campo al bloque
   BANDERA en el reader (decidido 2026-07-11). Erick ya lo tipó como
   `questions?: string[]` (lista) en `types.ts` con fallback a `text` —
   **Chang: usa esa forma exacta, `"questions": ["..."]`**, así el frontend no
   cambia nada. BANDERA sin `questions` = pausa visual, no dispara pregunta.
   **Ojo: aún no está en el reader.**
2. **Booleano** → correcto: `pending_question` + `pending_question_text`.
   El backend USA `pending_question_text` como la pregunta (obligatorio).
3. **Stream** → tokens como QA-RAG + `citations` (misma forma) + `evaluation`
   (arriba).
4. **Gatillo viewport** → sin objeción del backend; es decisión de UX del
   frontend.

### Consideraciones

- Latencia igual que QA-RAG (retrieval + 1 llamada al modelo de contenido).
  `CONTENT_MODEL` está en movimiento por la saturación de NIM: 70B → 49B
  nemotron (2026-07-11) → 8B (2026-07-12). Si vuelve un nemotron, el provider
  le inyecta `/no_think` automáticamente (razonan por defecto y eso
  duplica/triplica la latencia; medido 27s vs 10s). El "Pensando…" sin
  timeout del frontend aplica igual.
- La rama evaluación no toca `clarify_count`.
- Si el retrieval no devuelve nada dentro de la ventana anti-spoiler, la
  evaluación NO se aborta: da feedback prudente sin citar (citations `[]`).

### Probar en Postman

`POST /api/chat` con:

```json
{
  "book_id": "la_metamorfosis_franz_kafka",
  "message": "Se despertó convertido en un insecto y no podía levantarse",
  "agent_state": {
    "history": [],
    "clarify_count": 0,
    "pending_question": true,
    "pending_question_text": "¿En qué se convirtió Gregorio Samsa al despertar?"
  },
  "reading_state": { "focus_chunk_ids": [], "max_progress_chunk_index": 10 }
}
```

Esperable: `route: evaluacion` → tokens con feedback cálido → `citations`
con chunks ≤ 10 → `evaluation {attempt_detected: true}` → `done`.

## 2. Panel NER — `chunk_elements` en el reader

Nueva clave top-level **al final** del reader.json (aditiva, no rompe tipos
existentes), servida automáticamente por `GET /api/books/{book_id}/reader`:

```json
"chunk_elements": {
  "la_metamorfosis_franz_kafka::chunk::1": {
    "chunk_index": 1,
    "personajes": ["Gregorio Samsa"],
    "lugares": ["su habitación"],
    "objetos_simbolos": ["el cuadro de la dama"],
    "temas": ["transformación", "alienación"],
    "emociones": ["confusión"]
  },
  "...": {}
}
```

Taxonomía (decidida 2026-07-11): personajes, lugares, objetos_simbolos,
temas, emociones. Extraído por chunk con el modelo de contenido (49B).

### Panel implementado en el frontend (Erick: revísalo, es tuyo)

Por pedido de Giano (2026-07-12) implementé una primera versión del panel en
`frontend/` — sé que es territorio de Erick, así que va el detalle exacto para
que lo adopte, lo ajuste o lo rehaga:

- **`frontend/src/components/ElementsPanel.tsx`** (nuevo): tarjeta
  "📖 Elementos de la historia" colapsable. Agrega los `chunk_elements` hasta
  `max_progress_chunk_index`, en orden de primera aparición; chips por
  categoría (👤 📍 🗝️ 💭 🎭); los elementos presentes en `focus_chunk_ids`
  se resaltan (mismo amarillo que las citas) con tooltip "aparece en lo que
  estás leyendo". Fusiona variantes contenidas ("Gregorio" ⊂ "Gregorio
  Samsa" → la forma más larga; mínimo 4 letras para no fusionar palabras
  cortas). Libro sin anotar → el panel no se renderiza.
- **`frontend/src/components/ReaderView.tsx`**: la columna derecha ahora es
  `<div class="reader-side">` (sticky) con el panel arriba y el chat abajo.
- **`frontend/src/index.css`**: el sticky/height pasó de `.chat` a
  `.reader-side`; el chat es `flex: 1` dentro. Panel máx. 45% de la columna
  con scroll interno; en móvil (<900px) todo se apila y el chat vuelve a
  altura fija.
- **`frontend/src/api/types.ts`**: `ChunkElements` + `chunk_elements?` en
  `ReaderResponse` (opcional, no rompe el mock).
- Verificado: `npm run build` (tsc estricto + vite) en verde. NO actualicé
  el mock ni los e2e — si quieres probar el panel contra tu mock, sirve
  copiar un `chunk_elements` real del reader anotado.

### Mañas para el frontend

- **Anti-spoiler**: agrega al panel SOLO entradas con
  `chunk_index <= max_progress_chunk_index`. Por construcción cada entrada
  solo describe texto ya leído, así que el panel acumulado nunca spoilea.
- **Gate por VALOR del índice, no por conteo**: los índices de chunk tienen
  huecos (82 chunks, índice máximo 96 en la_metamorfosis).
- Las listas pueden venir vacías y máximo traen 5 items. `temas`/`emociones`
  en minúsculas; `personajes`/`lugares` conservan su casing.
- Un mismo personaje puede variar de forma entre chunks ("Gregorio" vs
  "Gregorio Samsa"): si acumulas un set global, normaliza en cliente o
  muestra la variante más larga.
- Por ahora SOLO la_metamorfosis está anotado (es el libro de trabajo).
- El reader está gitignorado: el `chunk_elements` viaja en el paquete de
  datos, no por git.

## 3. Para Chang

- **Pendiente tuyo**: campo `"question"` en los bloques BANDERA del reader
  (contrato decidido, ver §1). Aditivo.
- El extractor NER es reutilizable para tiempo de indexación:
  `companion.analysis.narrative_elements.NarrativeElementsExtractor` (módulo
  sin IO) + orquestación en `scripts/extract_narrative_elements.py`
  (resumible, cachea en `.llm_cache/`, `--force` para rehacer, `--limit N`
  para smoke test, `--workers N` llamadas en paralelo, default 6).
- **Latencia NIM (importante)**: el cliente OpenAI tenía el timeout default
  de 600s y NIM saturado dejaba requests COLGADOS (medido: chunks de 719s y
  1403s). `NvidiaLLMProvider` ahora corta a 90s por intento y reintenta —
  esto aplica a TODO (chat, evaluación, NER). Además el equipo bajó
  `CONTENT_MODEL` al 8B (2026-07-12) mientras dure la saturación.
- **Si regeneras el reader, la clave `chunk_elements` se pierde** → re-ejecuta
  `python scripts/extract_narrative_elements.py <book_id>` (con el cache LLM
  intacto tarda segundos).
- `QaRagOrchestrator` ganó `evaluate()` y un helper `_retrieve_scope()`
  compartido; tu `run()` de QA-RAG quedó intacto.

## Archivos tocados

- `src/companion/agent/tools/evaluate.py` — EvaluateTool (nuevo, estaba vacío)
- `src/companion/agent/orchestrator.py` — `evaluate()` + `_retrieve_scope()`
- `src/companion/agent/runtime.py` — rama `evaluacion` real + evento `evaluation`
- `src/companion/providers/nvidia_llm.py` — `/no_think` para modelos nemotron
  (latencia medida: 27s → 10s en el mismo prompt) + timeout de request de 90s
  (antes 600s default: requests colgados con NIM saturado)
- `src/companion/analysis/narrative_elements.py` — extractor NER (nuevo)
- `frontend/src/components/ElementsPanel.tsx` (+ ReaderView, types.ts,
  index.css) — panel NER en la UI, ver sección arriba
- `scripts/extract_narrative_elements.py` — CLI de anotación (nuevo)
- `data/outputs/readers/la_metamorfosis_franz_kafka.reader.json` — +`chunk_elements`
  (dato, gitignorado)