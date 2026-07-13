# Handoff — Vista de lectura, tracking de scroll y mock del backend

**Fecha:** 2026-07-11
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo)
**Referencia:** [`2026-07-11-frontend-api-client-catalogo.md`](2026-07-11-frontend-api-client-catalogo.md)

## Contexto

Segunda pieza del frontend: renderizado del reader y el cálculo de
`focus_chunk_ids` / `max_progress_chunk_index` a partir del scroll — los dos
valores que el backend necesita en cada request (handoff 2026-07-10 §3/§5).

## Qué se hizo

- **`frontend/src/components/ReaderView.tsx`** — renderiza los bloques en
  orden: `h1/h2/h3/p` como texto, `BANDERA` como pausa visual (la interacción
  real espera a la tool de EVALUACIÓN), paratexto (`is_narrative: false`)
  atenuado. La lista de bloques está memoizada: el scroll no re-renderiza el
  texto. Incluye una barra de desarrollo fija que muestra en vivo el estado
  de lectura que viajará al backend (se quitará antes de producción).
- **`frontend/src/hooks/useReadingTracker.ts`** — IntersectionObserver sobre
  cada bloque: `focus_chunk_ids` = chunk_ids distintos de los bloques visibles
  (ordenados por índice); `max_progress_chunk_index` = mayor N de los bloques
  que salieron del viewport por arriba, monótono. Bloques con `chunk_id: null`
  (BANDERA/paratexto) se ignoran, como pide el handoff.
- **`frontend/mock/server.mjs`** (`npm run mock`, puerto 8000) — mock del
  backend para desarrollar y demos de UI sin los datos reales: catálogo,
  reader sintético scrolleable (3 capítulos, 9 chunks, 1 BANDERA, paratexto),
  chat SSE con latencia simulada (rama qa_rag y rama imagen), imágenes async
  con 2 polls `pending` y SVG placeholder. Replica las asimetrías reales
  (poll_url absoluto en `/api/images`, relativo en la rama chat). El texto es
  sintético, no la obra real.

## Verificación

12 aserciones del cliente TS contra el mock: catálogo, forma del reader
(BANDERA con `chunk_id: null` y offsets `-1`), orden de eventos SSE,
re-ensamblado de tokens, citations, imagen directa (poll_url absoluto) e
imagen vía chat (poll_url relativo normalizado). `npm run build` estricto
pasa. El tracking por scroll se validará visualmente con la barra de
desarrollo (`npm run mock` + `npm run dev`).

## Decisión de alcance

`max_progress_chunk_index` sube cuando un bloque **sale del viewport por
arriba** (leído = dejado atrás), no al solo verlo. Coincide con la semántica
del handoff ("los bloques que el alumno ya dejó atrás"). Si el equipo
prefiere otra semántica (p. ej. contar el chunk visible más alto), es un
cambio de una línea — avisar por handoff.

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`.
