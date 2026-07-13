# Handoff — Secciones por BANDERA + flujo de evaluación en el chat (contrato a confirmar)

**Fecha:** 2026-07-11
**Autor:** agente de Erick (frontend)
**Para:** Giano (confirmar §3) / equipo
**Referencia:** [`2026-07-11-frontend-tracking-fix-e2e.md`](2026-07-11-frontend-tracking-fix-e2e.md)

## Contexto

El equipo aclaró a Erick (verbal, 2026-07-11): las secciones NO son capítulos,
son tramos anotados por el profesor cuyo fin marca cada BANDERA; al llegar el
foco del lector al fin de sección se gatilla una evaluación; la pregunta la
tiene el frontend y la despliega en el chat; la respuesta del alumno viaja a
`/api/chat` con el booleano de pregunta pendiente; y todo se maneja por
chunks. El frontend quedó alineado a eso.

## 1. Corregido: secciones = tramos entre BANDERAs

`IllustrateBar` derivaba las secciones de los `h2` (capítulos) — supuesto mío,
equivocado. Ahora una sección = chunks entre banderas (la N se abre tras la
bandera N-1). El botón "esta sección" manda los `chunk_ids` del tramo anotado
que el alumno está viendo. Tooltip corregido.

## 2. Nuevo: flujo de evaluación (cableado y verificado contra mock)

1. La BANDERA con pregunta entra al viewport → la pregunta se despliega en el
   chat ("📋 Pregunta de comprensión: …"), una sola vez por bandera.
2. `agent_state.pending_question = true` y `pending_question_text` = la
   pregunta. El siguiente mensaje del alumno viaja con eso (el router ya
   recibe `pending_question` en `Router.decide`).
3. Tras un stream exitoso el flag baja (una pregunta se responde una vez);
   si el request falla, se mantiene para reintentar.
4. Si la BANDERA aún trae el marcador crudo `--$CHECKPOINT_LECTURA$--`, es
   solo pausa visual (fallback, no rompe nada).

E2E con Playwright ampliado a 16 checks: incluye scroll hasta la bandera →
pregunta en chat → respuesta → `route: evaluacion` → feedback, y que la
bandera sin pregunta no genera mensaje.

## 3. ⚠️ Contrato PROPUESTO — Giano, confirma o corrige

Cableé el flujo con estos supuestos; dime cuáles van mal y lo ajusto:

1. **¿Dónde viaja la pregunta del profe?** Supuse: como `text` del bloque
   BANDERA en el reader (hoy llega el marcador crudo). Si va a ser otro campo
   (p. ej. `question` en el bloque, o endpoint aparte), es un cambio chico en
   `checkpointQuestion()` de `frontend/src/api/types.ts`.
2. **Booleano**: uso `agent_state.pending_question` + `pending_question_text`
   (los campos reservados de `AgentState`). ¿Correcto?
3. **Respuesta de EVALUACIÓN**: asumí que streameará `token`s como QA-RAG
   (así lo simula el mock). Si va a emitir eventos propios (p. ej. rúbrica,
   nota), avísame para reservar la UI.
4. **Gatillo**: "fin de sección" = la BANDERA entra al viewport. ¿O prefieren
   otro criterio (p. ej. bandera dejada atrás)?

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`.
