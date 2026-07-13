# Handoff — Fix checkpointQuestion para leer preguntas de block.questions

**Fecha:** 2026-07-12
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo)
**Referencia:** [`2026-07-11-frontend-fix-gotclarify-tracking.md`](2026-07-11-frontend-fix-gotclarify-tracking.md)

## Contexto

Los readers actualizados traen las preguntas de comprensión en
`block.questions[0]` (arreglo), pero el frontend buscaba la pregunta en
`block.text` (que contiene el marcador crudo `--$CHECKPOINT_LECTURA$--`).
Resultado: las preguntas nunca se mostraban.

## Cambio

**Archivo:** `frontend/src/api/types.ts`

1. Se agregó `questions?: string[]` a la interfaz `ReaderBlock`.
2. `checkpointQuestion()` ahora lee de `block.questions[0]` en vez de
   `block.text`.

```typescript
// Antes
export function checkpointQuestion(block: ReaderBlock): string | null {
  if (block.type !== "BANDERA") return null;
  const text = block.text.trim();
  if (!text || text === CHECKPOINT_MARKER) return null;
  return text;
}

// Ahora
export function checkpointQuestion(block: ReaderBlock): string | null {
  if (block.type !== "BANDERA") return null;
  if (block.questions && block.questions.length > 0) {
    return block.questions[0];
  }
  return null;
}
```

## Verificación

- `npm run build` → OK
- Validación manual: las 392 preguntas de comprensión (8 libros) se
  despliegan correctamente en el chat al llegar a cada BANDERA.

## Datos incorporados

Se copiaron desde `source_reader_companion/`:
- 8 master files → `data/master/`
- 8 reader files → `data/outputs/readers/`
- chroma_db_V1 → `chroma_db/`

## Contrato resultante

El campo `questions` en los readers es un arreglo de strings. El frontend
toma solo `questions[0]`. Si el equipo decide enviar múltiples preguntas
por BANDERA, el frontend ya está preparado para mostrar solo la primera.

## Qué NO toqué

Nada fuera de `frontend/src/api/types.ts` y `agent_log/`.
