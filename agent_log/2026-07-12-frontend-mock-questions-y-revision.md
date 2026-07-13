# Handoff — Mock alineado a block.questions[] + cierre de la revisión general

**Fecha:** 2026-07-12
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo)
**Referencia:** [`2026-07-12-frontend-fix-checkpoint-question.md`](2026-07-12-frontend-fix-checkpoint-question.md)

## 1. Fix: el mock quedó desalineado del contrato de preguntas

El fix del 2026-07-12 (leer preguntas de `block.questions[0]`) actualizó
`types.ts` pero no `frontend/mock/server.mjs`, que seguía mandando la
pregunta en el `text` de la BANDERA. Resultado: contra el mock, el flujo de
checkpoint quedó roto (el e2e lo detectó: timeout esperando el feedback de
evaluación). El mock ahora emite `questions: [...]` con `text` = marcador
crudo, igual que los readers reales. E2E de vuelta en verde (16 checks) y
suite del cliente (13) también.

Lección para el equipo: el mock es parte del contrato — cualquier cambio de
contrato debe tocar types.ts + mock + e2e en el mismo commit, y `npm run
e2e:tracking` es el guardián de eso.

## 2. Cierre de la revisión general del branch

Se corrió una revisión multi-ángulo del diff completo vs `origin/dev`
(correctness línea a línea, comportamiento eliminado, cruce con el contrato
del backend real, reuso, simplificación, eficiencia, convenciones).

**Corregido durante la revisión** (commits `bc2737a`, `8bedcc7` y este):
- Semántica de `max_progress_chunk_index` = "hasta donde leyó" (incluye lo
  visible), alineada con la definición del equipo.
- Race condition: un checkpoint disparado durante un stream en curso ya no
  pierde su `pending_question` por el reset post-stream.
- `gotClarify` muerto eliminado; ids de mensajes con `useRef` (HMR-safe).
- Cross-check del contrato frontend ↔ backend real (`api/*.py`, `state.py`,
  `runtime.py`, `contracts.py`): sin desajustes.
- Convenciones: todos los commits dentro de `frontend/` + `agent_log/` y con
  handoff (el commit `e42089a` que tocó backend fue revertido en `19c10d4`,
  correcto según las reglas de propiedad).

**Pendientes aceptados** (deuda registrada, no bloqueante — ver findings del
reporte de revisión): unificar el ciclo de vida de los dos
IntersectionObservers en un hook compartido; extraer helper común de
poll-de-imagen (ChatPanel/IllustrateBar); memoizar ChatBubble y sacar
readingState del render del chat (perf en hardware escolar); compartir
TOP/BOTTOM_OFFSET con el e2e desde un módulo; liberar bloques del Map al
cambiar de libro.

## 3. Estado del proyecto

Datos reales incorporados (8 libros, 392 preguntas, chroma_db local): el
backend real ya puede correr en esta máquina. Siguiente paso natural:
levantar el backend real y validar la integración de verdad (catálogo,
reader y preguntas funcionan sin API key; chat/imágenes reales requieren
credenciales NVIDIA/Cloudflare en `.env`).

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`.
