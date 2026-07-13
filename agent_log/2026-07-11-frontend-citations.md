# Handoff — Citations resaltadas en el texto + navegación a la fuente

**Fecha:** 2026-07-11
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo)
**Referencia:** [`2026-07-11-frontend-chat-imagenes.md`](2026-07-11-frontend-chat-imagenes.md)

## Contexto

Cierre del ciclo QA-RAG en la UI: las `citations` que emite el backend al
final del stream ahora se ven en el texto, usando los offsets absolutos del
contrato (contrato #2 de AGENTS.md: `char_start`/`char_end` sobre el texto
canónico).

## Qué se hizo

- **Resaltado**: al llegar el evento `citations`, los bloques del reader que
  intersectan los rangos citados se pintan (mismo `chunk_id` + solapamiento
  de offsets bloque↔cita). Si una cita llega sin rango útil
  (`char_end <= char_start`, el default del contrato es 0/0), se cae a
  resaltar el chunk completo.
- **Navegación**: el chip "📖 Fuentes: chunk N" bajo la respuesta es un botón;
  al clickearlo la vista hace scroll suave hasta el primer bloque citado.
  El resaltado al llegar la respuesta NO mueve el scroll (no robarle la
  posición de lectura al alumno); solo el click navega.
- **Mock**: la cita ahora apunta a un bloque real de los `focus_chunk_ids`
  del request (con sus offsets verdaderos), para que el resaltado sea
  verificable visualmente.
- Copy de la BANDERA aclarado: "aparecerá una pregunta de comprensión cuando
  la evaluación esté disponible (próximamente)" — Erick la probó esperando la
  pregunta; hasta que EVALUACIÓN exista, el checkpoint es solo visual.

## Granularidad (decisión y posible mejora futura)

El resaltado es **por bloque**, no por caracteres dentro del bloque: los
offsets de las citas se comparan contra los offsets de los bloques y se pinta
el bloque entero. Resaltar sub-rangos dentro de un párrafo requiere partir el
texto del bloque con los offsets relativos — factible (los offsets absolutos
lo permiten), pero se pospone hasta ver citas reales del QA-RAG: si el
backend suele citar chunks completos, no vale la complejidad.

## Verificación

13 aserciones contra el mock en verde; `npm run build` estricto pasa;
smoke visual con `npm run mock` + `npm run dev`.

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`.
