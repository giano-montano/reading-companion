# Handoff — Cliente TS del contrato de la API + catálogo de libros

**Fecha:** 2026-07-11
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo + 1 pregunta para Chang/Rodri al final)
**Referencia:** [`2026-07-10-handoff-frontend-erick.md`](2026-07-10-handoff-frontend-erick.md),
[`2026-07-11-frontend-scaffold-stack.md`](2026-07-11-frontend-scaffold-stack.md)

## Contexto

Primera pieza funcional del frontend: capa de API tipada (contrato completo)
y la vista de catálogo. El contrato se tipó leyendo el código real de la rama
(`api/books.py`, `api/chat.py`, `api/images.py`, `agent/state.py`,
`agent/runtime.py`, `contracts.py`), no solo el handoff.

## Qué se hizo

- **`frontend/src/api/types.ts`** — contrato completo en TypeScript:
  `BookSummary`, `ReaderBlock`/`ReaderResponse`, `AgentState`/`ReadingState`
  (con los defaults del backend), `ChatEvent` como unión discriminada de los
  8 eventos SSE, `ImageRequest` (4 scopes) y estados de job. Los campos en
  desuso (`last_completed_section`, `max_progress_section`) se excluyeron del
  tipo a propósito para que nadie los cablee.
- **`frontend/src/api/client.ts`** — una función por endpoint:
  `getBooks`, `getReader`, `createImageJob`, `getImageJob`,
  `pollImageJob` (abortable) y `streamChat` (fetch + `getReader()`, parser de
  frames SSE). Cubre las mañas #1 (SSE por POST), #2 (sin timeout propio) y
  #8 (`resolvePollUrl` normaliza el poll_url relativo de la rama chat).
- **`frontend/src/components/BookCatalog.tsx`** — catálogo con estados
  cargando/error/vacío/listo; `App.tsx` maneja la selección (la vista de
  lectura es la siguiente iteración).

## Verificación

Sin datos locales no se puede levantar el backend real (ver pregunta abajo),
así que se verificó contra un **mock en Node que replica el contrato**
(frames SSE crudos con `event:`/`data:`, imagen async con 2 polls `pending`
antes de `done`, `poll_url` relativo a propósito). 7 aserciones pasaron:
catálogo tipado, orden `route`→…→`done`, re-ensamblado de tokens, citations
con offsets, job encolado, normalización de poll_url y polling hasta `done`.
`npm run build` (tsc estricto + vite) también pasa. El mock vive en el
scratchpad del agente, no en el repo.

## Pregunta para Chang/Rodri (no bloqueante todavía)

`data/master/*.json` y `data/outputs/readers/` están gitignorados (regla
`*.json` del `.gitignore` raíz), así que en la máquina de Erick el backend
arrancaría sin libros. Para integrar de verdad necesitamos una de dos:
(a) que nos pasen el paquete de datos generado (master + readers + chroma_db)
por fuera de git, o (b) instrucciones mínimas para regenerarlo con
`src/preprocesamiento/` desde los EPUB. ¿Cuál prefieren? Mientras tanto
seguimos contra el mock.

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`. El mock de verificación no se
commiteó.
