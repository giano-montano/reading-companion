# Handoff para el frontend (Erick + agente)

**Fecha:** 2026-07-10
**Autor:** agente de Giano
**Para:** Erick + su agente de frontend
**Backend relacionado:** [`2026-07-10-api-chat-images-endpoints.md`](2026-07-10-api-chat-images-endpoints.md)

Este doc es autocontenido para armar el frontend. Explica lo que ya funciona,
cómo consumirlo, las trampas que te van a morder, y qué va a cambiar.

---

## 1. Modelo mental del producto

Un compañero de lectura para secundaria. El alumno **lee la obra en pantalla** y
puede: (a) preguntar por chat, (b) pedir una **imagen** de lo que ve. El backend
es **sin sesión persistente**: es stateless, el **frontend es dueño del estado**
(historial, progreso de lectura) y lo manda en cada request. Si recargas la
pestaña, se pierde (por diseño, MVP).

El backend nunca decide qué ve el alumno: eso lo calcula el frontend a partir del
scroll y se lo pasa como contexto explícito. El LLM jamás fija el progreso.

---

## 2. Endpoints disponibles

| Método | Ruta | Para qué |
|---|---|---|
| `GET`  | `/api/books` | catálogo de libros |
| `GET`  | `/api/books/{book_id}/reader` | el texto del libro (bloques) para renderizar |
| `POST` | `/api/chat` | chat (SSE): pregunta → respuesta, o "dibújame esto" → job de imagen |
| `POST` | `/api/images` | generar imagen por scope explícito (botones), devuelve `job_id` |
| `GET`  | `/api/images/{job_id}` | poll del estado de la imagen |
| `POST` | `/api/visual-support` | (legacy) imagen síncrona desde `text` crudo |

Base URL en dev: `http://localhost:8000`. **CORS abierto**, puedes pegarle
directo desde el navegador.

---

## 3. Renderizar el libro (`/api/books/{id}/reader`)

Respuesta:
```json
{
  "book_id": "la_metamorfosis_franz_kafka",
  "metadata": { "title": "...", "author": "...", "publication_year": 2022 },
  "blocks": [
    { "id_block": "...::block::3", "type": "h2", "text": "Capítulo 1",
      "chunk_id": "la_metamorfosis_franz_kafka::chunk::1",
      "char_start": 30, "char_end": 40, "is_narrative": true }
  ]
}
```

Cada bloque tiene: `id_block`, `type` (`h1|h2|h3|p|BANDERA`), `text`,
`is_narrative`, `char_start`, `char_end`, `chunk_id` (**string** `libro::chunk::N`
o `null`).

- **Itera `blocks` en orden** = orden de lectura.
- `type` decide el render: `h*` = encabezado, `p` = párrafo, `BANDERA` = **no es
  texto**, es un checkpoint pedagógico (pausa; muestra una interacción, no el
  texto `--$CHECKPOINT_LECTURA$--`).
- `is_narrative: false` = paratexto (portada, créditos). Puedes ocultarlo o
  atenuarlo.
- Bloques `BANDERA`: `chunk_id: null`, `char_start/end: -1`. **Ignóralos** al
  calcular progreso/foco.

### 🔑 El `chunk_id` es tu moneda de cambio

Varios bloques consecutivos comparten `chunk_id`. **De aquí sacas los dos valores
que el backend necesita** (ver §5):
- **`focus_chunk_ids`** = los `chunk_id` distintos de los bloques visibles en el
  viewport.
- **`max_progress_chunk_index`** = el mayor `N` (sufijo entero de `::chunk::N`)
  entre los bloques que el alumno ya dejó atrás (leídos).

---

## 4. Chat (`POST /api/chat`) — SSE

### ⚠️ Maña #1: es SSE por POST → NO uses `EventSource`

`EventSource` solo hace GET. Este endpoint es POST con body. Consúmelo con
`fetch` + lector de stream:

```js
const res = await fetch("http://localhost:8000/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buf = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  // parsea frames separados por "\n\n": líneas "event: X" y "data: {json}"
  let i;
  while ((i = buf.indexOf("\n\n")) !== -1) {
    const frame = buf.slice(0, i); buf = buf.slice(i + 2);
    const ev = frame.match(/^event: (.+)$/m)?.[1];
    const data = JSON.parse(frame.match(/^data: (.+)$/m)?.[1] || "{}");
    handle(ev, data);
  }
}
```

### Request

```json
{
  "book_id": "la_metamorfosis_franz_kafka",
  "message": "¿En qué se convirtió Gregorio?",
  "agent_state":   { "history": [], "clarify_count": 0, "pending_question": false },
  "reading_state": { "max_progress_chunk_index": 20, "focus_chunk_ids": ["...::chunk::20"] }
}
```

### Eventos que puedes recibir

| event | payload | qué hacer |
|---|---|---|
| `route` | `{tool}` | primer evento; te dice la rama (`qa_rag`/`imagen`/`clarify`/...) |
| `token` | `{delta}` | (qa_rag) concatena `delta` y ve pintando la respuesta |
| `citations` | `{citations:[{chunk_id,char_start,char_end}], answered, ok}` | (qa_rag) al final; usa offsets para resaltar fuentes en el texto |
| `clarify` | `{clarification, clarify_count}` | muestra el texto y **guarda `clarify_count`** (ver maña #3) |
| `image_job` | `{job_id, poll_url}` | (imagen) arranca el poll de `/api/images/{job_id}` |
| `notice` | `{tool, message}` | rama no implementada o sin contexto; muestra el `message` |
| `error` | `{message}` | fallo controlado; cierra con `done` igual |
| `done` | `{}` | siempre el último; corta el loop |

### ⚠️ Maña #2: latencia del modelo (~90s)

El modelo de contenido (70B) tarda ~90s en responder, y **el streaming es
simulado**: hoy no verás tokens gotear en tiempo real, sino que tras la espera
llegan casi de golpe. Diseña un estado "pensando…" con spinner y **no pongas
timeout corto** en el fetch. Esto mejorará cuando el backend meta streaming real
o un modelo más rápido — **el contrato de eventos no cambiará**.

### Pedir imagen desde el chat

Si `message` es tipo "dibújame esto", `route` sale `imagen` y recibes
`image_job`. El backend ilustra **lo que ves** → por eso el `reading_state` debe
traer `focus_chunk_ids`. Si van vacíos, recibes un `notice`.

---

## 5. Estado que el frontend debe mantener y reenviar

El backend es **stateless**: no recuerda nada entre requests. Tú llevas el estado
y lo mandas siempre.

### `agent_state`
- `history`: `[{role:"user"|"assistant", content}]`. Tras cada intercambio,
  **appende** el turno del alumno y la respuesta del asistente. El backend usa
  los últimos ~5 pares para contexto conversacional.
- `clarify_count`: entero. **⚠️ Maña #3:** cuando llega un evento `clarify`,
  guarda el `clarify_count` que trae y **mándalo en la siguiente request**. Si no
  lo haces, el router pedirá aclaración para siempre; con el conteo, tras 1–2
  intentos cae por defecto a QA-RAG. Reinícialo a 0 cuando haya una interacción
  exitosa.
- `pending_question` / `pending_question_text`: reservados para la tool de
  **Evaluación** (aún no implementada). Déjalos en `false`/`""` por ahora.

### `reading_state`
- `focus_chunk_ids` (list[str]): chunk_ids visibles ahora → para imagen "lo que
  veo".
- `max_progress_chunk_index` (int): hasta dónde ha leído → **anti-spoiler** de
  QA-RAG. `0`/ausente = sin filtro. **Súbelo monótonamente** con el scroll (nunca
  baja). Es el número final de `::chunk::N`.
- `last_completed_section`, `max_progress_section`: **ignóralos**, son de un eje
  viejo (secciones) que quedó en desuso. El eje real es `chunk_index`.

---

## 6. Imágenes directas (botones) — `POST /api/images`

Patrón **async de 2 pasos**: encolas → haces poll.

### Paso 1 — encolar
```json
{
  "book_id": "la_metamorfosis_franz_kafka",
  "scope": "vista",
  "chunk_ids": ["...::chunk::1", "...::chunk::2"],
  "mock": false
}
```
Respuesta `202`:
```json
{ "job_id": "f0e1...", "poll_url": "http://localhost:8000/api/images/f0e1...", "status": "pending" }
```

### Paso 2 — poll (`GET poll_url` cada ~1–2s)
```json
{ "job_id":"f0e1...", "status":"done",
  "image_url":"http://localhost:8000/generated-visuals/visual_xxx.png",
  "error": null, "meta": { "provider":"cloudflare", "frame_count":1, ... } }
```
`status` ∈ `pending | done | error`. Cuando `done`, pinta `image_url`. Cuando
`error`, muestra `error` (p.ej. cuota de Cloudflare agotada → `429`).

### Los 4 scopes (mapea tus botones)
| botón | `scope` | campos |
|---|---|---|
| "lo que veo" | `vista` | `chunk_ids` (visibles) |
| "esta sección" | `seccion` | `chunk_ids` (los de la sección) |
| "hasta aquí" | `hasta_maximo` | `max_progress_chunk_index` |
| "toda la obra" | `obra` | — |

Opcionales: `width`, `height`, `seed`, `title`, `characters`, `visual_events`,
`allow_text_in_image`, `mock`.

### ⚠️ Maña #4: el flag `mock` (tri-estado)
- `"mock": true` → SVG placeholder gratis e instantáneo (para maquetar la UI).
- `"mock": false` → **Flux real** (tarda, cuesta, puede dar `429`). **Fuerza real
  aunque el flag global esté en true.**
- Ausente/`null` → sigue el default global del server (`VISUAL_MOCK_ENABLED`). En
  dev ese flag suele estar en `true`, así que **si quieres imagen real, manda
  explícitamente `"mock": false`**.

### ⚠️ Maña #5: imágenes reales — flag de contenido y latencia variable
- Flux corre un clasificador de seguridad sobre la imagen generada. Si la marca
  (`code 3030`), el backend **reintenta solo con otro seed** (hasta 3 veces). Por
  eso una imagen real puede tardar bastante o, si el fragmento es persistentemente
  marcado, terminar en `status: "error"` con un mensaje claro ("...no apta tras 3
  intentos..."). No es un fallo del frontend: muestra el `error` y ofrece
  reintentar o cambiar de fragmento.
- El `seed` por defecto es fijo (`12345`) → imágenes deterministas y cacheadas
  (no re-cobra por el mismo fragmento). Si quieres variación deliberada, manda un
  `seed` distinto.

---

## 7. Trampas del backend que te van a morder (resumen)

1. **SSE por POST ≠ EventSource.** Usa `fetch` + `getReader()` (maña #1).
2. **~90s de latencia** en QA-RAG; streaming simulado (maña #2). Estado "pensando".
3. **`clarify_count` hay que reenviarlo** o el router se atasca (maña #3).
4. **`mock: false` explícito** para imagen real (maña #4).
5. **`image_url` es absoluta**, construida desde el host de la request. Detrás de
   un proxy/túnel, si el host que ve el backend no es el público, la URL saldrá
   con `localhost`. En dev directo no hay problema.
6. **Imágenes = 2 pasos siempre** (encolar + poll). No hay push; haces polling.
7. **El job store vive en memoria** de un solo proceso. Si reinicias el server o
   corres varios workers, los `job_id` viejos se pierden. Para dev está bien.
8. **`poll_url` inconsistente entre rutas:** en `/api/chat` el `image_job` trae
   `poll_url` **relativo** (`/api/images/{id}`); en `/api/images` viene
   **absoluto**. Normaliza en el cliente (antepón el origin si empieza por `/`).
9. **Imagen real puede fallar por content-flag** (maña #5): status `error` con
   mensaje amigable; ofrece reintentar/cambiar fragmento. Y puede tardar más de lo
   esperado por los reintentos internos de seed.

---

## 8. Lo que NO está y probablemente cambiará

- **RESUMIR, GRAFO, EVALUACIÓN** → hoy devuelven `notice` "no disponible". No
  construyas UI final asumiendo su forma todavía (el grafo ni siquiera tiene
  datos: falta `graph.json`).
- **Streaming real de tokens** → llegará; el contrato de eventos se mantiene.
- **Modelo más rápido / más barato** → en evaluación; puede cambiar la latencia,
  no la API.
- **Calidad del retrieval (QA-RAG)** → en mejora (preguntas hipotéticas + posible
  reranker). Las respuestas pueden ser flojas en algunos libros por ahora; no es
  bug de integración.
- **Sesión persistente** → no existe (MVP). Si más adelante se añade, `agent_state`
  podría dejar de viajar completo en cada request.

---

## 9. Flujo E2E mínimo para el MVP

1. `GET /api/books` → pinta el catálogo, el usuario elige uno.
2. `GET /api/books/{id}/reader` → renderiza los bloques; trackea scroll para
   calcular `focus_chunk_ids` y `max_progress_chunk_index`.
3. Chat: `POST /api/chat` con el mensaje + `agent_state` + `reading_state`;
   consume el SSE; actualiza `history` (y `clarify_count` si aplica).
4. Botón de imagen: `POST /api/images` con el scope; haz poll a `poll_url` hasta
   `done`; muestra `image_url`.

Dudas de contrato → pregúntame (agente de Giano) antes de asumir; algunos campos
(`*_section`, `pending_question`) son placeholders y no deben cablearse aún.

---

## 10. Ping-pong entre agentes: cómo reportar de vuelta

El equipo trabaja con handoffs en `agent_log/`. Para que el ida y vuelta sea
limpio, cuando tu agente (frontend) encuentre una tensión, bug o necesite un
ajuste del backend, **NO edites el backend**: escribe un handoff y deja que el
dueño del archivo lo aplique.

### Reglas de propiedad (quién toca qué)
- **Backend de agente/API** (`src/companion/agent/**`, `src/companion/api/**`,
  `src/companion/scope/**`, `src/companion/visual_support/**`, `contracts.py`) →
  **de Giano**. Propón cambios, no los apliques.
- **Preprocesamiento / datos / retrieval / Chroma** (`src/preprocesamiento/**`,
  `data/**`, embeddings) → **de Chang/Rodri**.
- **Frontend** → tuyo.

Regla de oro: **dos agentes no editan el mismo archivo.** Si necesitas un cambio
en un archivo ajeno, se pide por handoff y lo aplica su dueño.

### Formato del handoff de vuelta
Crea `agent_log/AAAA-MM-DD-frontend-<tema>.md` con:

```markdown
# Handoff — <tema> (frontend → backend)
**Fecha:** ...  **Autor:** agente de Erick  **Para:** Giano / Chang

## Contexto
Qué estabas integrando cuando apareció esto.

## Hallazgo
Tensión / bug / ajuste. Sé concreto:
- Endpoint + request exacto (JSON) que enviaste.
- Respuesta / eventos SSE que recibiste (pega el crudo).
- Qué esperabas vs qué pasó.

## Impacto
Qué bloquea o degrada en el frontend.

## Propuesta (opcional)
Cómo crees que debería resolverse, y en qué archivo (marca de quién es).

## Qué NO toqué
Confirma que no editaste archivos ajenos.
```

### Cómo dar un buen reporte reproducible
1. **Pega el request y la respuesta crudos**, no los parafrasees. Para SSE, pega
   los frames `event:`/`data:` tal cual.
2. **Un hallazgo por handoff** (o una lista clara y numerada). No mezcles 5 cosas.
3. **Distingue** "esto es un bug del backend" de "esto es un contrato ambiguo que
   necesito que definan" de "esto es una mejora que propongo".
4. **Estado esperado**: si es algo diferido (RESUMIR/GRAFO/EVALUACIÓN), no lo
   reportes como bug; pregunta por el timeline.
5. Si es urgente y bloqueante, dilo en el título: `[BLOQUEANTE]`.

Con eso, el agente del backend puede leer, reproducir con tu JSON, y devolverte
un handoff de resolución sin adivinar. Ping-pong limpio.
