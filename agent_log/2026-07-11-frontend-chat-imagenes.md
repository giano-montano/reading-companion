# Handoff — Chat SSE + botones de ilustración (flujo E2E del MVP completo contra mock)

**Fecha:** 2026-07-11
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo)
**Referencia:** [`2026-07-11-frontend-reader-tracking-mock.md`](2026-07-11-frontend-reader-tracking-mock.md)

## Contexto

Tercera pieza: chat y generación de imágenes. Con esto el flujo E2E mínimo del
MVP (handoff 2026-07-10 §9) está completo en el frontend: catálogo → lectura
con tracking → chat SSE → imágenes por scope. Todo verificado contra el mock;
falta la integración con el backend real (bloqueada por los datos, ver
handoff anterior).

## Qué se hizo

- **`frontend/src/components/ChatPanel.tsx`** — chat lateral. Es el dueño del
  `agent_state`: acumula `history` (máx 5 pares, igual que el backend),
  guarda y reenvía `clarify_count` cuando llega un `clarify` (maña #3) y lo
  reinicia a 0 tras una interacción exitosa. Consume el stream: "Pensando…"
  hasta el primer token (maña #2, sin timeout), pintado incremental, fuentes
  de `citations` con número de chunk, `notice`/`error` como avisos, y la rama
  imagen hace su polling y muestra la ilustración dentro del chat.
- **`frontend/src/components/IllustrateBar.tsx`** — los 4 botones → scopes:
  "lo que veo" (`vista` + focus), "esta sección" (`seccion` + chunks de la
  sección actual), "hasta aquí" (`hasta_maximo`), "toda la obra" (`obra`).
  Los botones se deshabilitan si su scope no tiene datos aún (p. ej. `vista`
  sin chunks visibles). Resultado en una tarjeta flotante con estados
  generando/listo/error.
- **Derivación de secciones:** el reader no trae número de sección por bloque,
  así que la sección se deriva en el cliente: se abre una nueva en cada `h2`.
  Si el backend prefiere exponer la sección explícita en los bloques, mejor —
  propuesta abierta, no bloqueante.
- **`mock/server.mjs`**: nueva rama `clarify` (mensajes < 6 chars, hasta 2
  veces, como el router real) para probar la maña #3 desde la UI.
- **`mock: false` NO se envía todavía**: los botones dejan el default del
  server (maña #4). Cuando toque probar Flux real, se añade un toggle de UI.

## Verificación

13 aserciones contra el mock (las 12 previas + clarify con conteo
incrementado). `npm run build` estricto pasa. Smoke test del lanzamiento:
`npm run mock` + `npm run dev` levantan y responden (catálogo por HTTP y app
en :5173). Nota operativa: si el puerto 8000 queda ocupado por una instancia
vieja del mock, el nuevo muere con `EADDRINUSE` y se sigue sirviendo el
código viejo — matar el proceso anterior antes de relanzar.

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`.
