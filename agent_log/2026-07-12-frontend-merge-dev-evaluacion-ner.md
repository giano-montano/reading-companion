# Handoff — Merge de dev: evaluación real + panel NER adoptado

**Fecha:** 2026-07-12
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo; gracias Giano por el handoff detallado)
**Referencia:** [`2026-07-11-backend-evaluacion-ner-panel.md`](2026-07-11-backend-evaluacion-ner-panel.md),
[`2026-07-12-frontend-gate-evaluacion-ux.md`](2026-07-12-frontend-gate-evaluacion-ux.md)

## Qué se integró

Merge de `origin/dev` (`952b6b4` evaluación + NER + fixes NIM, `d24df12`
datos) en `feature/frontend`.

### Conflictos y cómo se resolvieron

- **`ReaderView.tsx`**: dev traía el panel NER integrado sobre una versión
  ANTERIOR de nuestro ReaderView (sin el gate anti scroll-dump). Resolución:
  nuestra versión con gate como base + el envoltorio `.reader-side`
  (ElementsPanel arriba, chat abajo) de Giano. Conviven sin fricción.
- **`types.ts`**: se tomó la versión de dev (agrega `ChunkElements`,
  `chunk_elements?` en el reader, y un `checkpointQuestion` con fallback a
  `text` — más tolerante que el nuestro).
- **`mock/server.mjs`**: fusión manual; banderas ahora con
  `is_narrative: false` (como dev).

### Adopción del panel NER (era nuestro territorio, Giano lo sabía)

`ElementsPanel` adoptado tal cual: el diseño respeta el anti-spoiler por
valor de `chunk_index` y encaja con nuestro `readingState`. Gracias por el
detalle del handoff — no hizo falta rehacer nada.

### Complementos del frontend en este merge

- Evento `evaluation {attempt_detected, ok}` agregado a `ChatEvent` en
  `types.ts` (aditivo; la UI hoy lo ignora — cuando queramos un badge de
  "intento válido" el tipo ya está).
- **Mock actualizado como espejo del backend real**: rama evaluación ahora
  emite `citations` (vacías) + `evaluation` antes de `done`, y el reader
  mock trae `chunk_elements` de muestra para desarrollar el panel sin datos.
- **E2E ampliado a 24 checks**: nuevo check de que el panel renderiza los
  `chunk_elements`.
- **`pnpm-lock.yaml` eliminado**: el frontend usa npm (`package-lock.json`
  ya versionado). Dos lockfiles divergentes rompen instalaciones
  reproducibles. Giano: si prefieres pnpm lo conversamos, pero uno solo.

## Verificación

`npm run build` y e2e completo (24 checks) en verde contra el stack aislado
(mock :8123 + vite :5199). La evaluación real (backend) queda por probar
manualmente: **recuerden reiniciar el uvicorn** — el proceso corriendo sirve
el código de antes del merge.

## Qué NO toqué

Backend intacto (el merge trae los cambios de Giano tal cual). Fuera de eso,
solo `frontend/` y `agent_log/`.
