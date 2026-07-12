# Handoff — Chat más ancho + input multilínea + diagnóstico de imágenes

**Fecha:** 2026-07-12
**Autor:** agente de Erick (frontend)
**Para:** equipo — §3 (imágenes) es para Giano/quien administre el `.env`.
**Referencia:** [`2026-07-12-frontend-merge-dev-evaluacion-ner.md`](2026-07-12-frontend-merge-dev-evaluacion-ner.md)

## 1. Chat más ancho

La columna lateral pasó de `360px` fija a `minmax(400px, 460px)` y el ancho
máximo del lector de `1200px` a `1400px`. Con esto los fragmentos de
pregunta/respuesta ocupan menos líneas y se scrollea menos. En móvil
(<900px) sigue apilándose como antes.

## 2. Input del chat: multilínea con auto-grow

`<input>` → `<textarea>`:
- Crece con el texto hasta ~5-6 líneas (luego scrollea dentro del campo) y
  vuelve a una línea al enviar.
- **Enter envía; Shift+Enter inserta salto de línea**, para que el alumno
  revise y corrija preguntas largas antes de mandarlas. El placeholder lo
  explica.
- El botón "Enviar" se ancla abajo cuando el campo crece.
- Actualizados los consumidores del selector viejo (`.chat-input input` →
  `textarea`): el foco desde el gate y los 4 usos del e2e.

## 3. ⚠️ Imágenes: por qué salen placeholders (config, no código)

Las imágenes SÍ se generan, pero son **SVG placeholder**, no Flux real. Dos
causas, ambas en el `.env` del backend (no en el frontend):

1. **`VISUAL_MOCK_ENABLED=true`** → el backend devuelve el SVG de relleno por
   defecto. El frontend no manda `mock:false` (respeta el default global,
   como se acordó), así que siempre cae en mock.
2. **`CLOUDFLARE_ACCOUNT_ID=` vacío** → aunque se fuerce real,
   `CloudflareFluxProvider.__init__` lanza `ValueError("CLOUDFLARE_ACCOUNT_ID
   no configurado")`. El `CLOUDFLARE_API_TOKEN` sí está; falta el account id.

**Para activar imágenes reales (en la máquina de Erick, `.env`):**
- Rellenar `CLOUDFLARE_ACCOUNT_ID=<id de la cuenta Cloudflare>`.
- Poner `VISUAL_MOCK_ENABLED=false` (o dejar que el frontend mande
  `mock:false` — ver decisión abajo). Reiniciar el uvicorn.

**Decisión pendiente para el equipo:** ¿los botones de ilustrar deben forzar
`mock:false` desde el frontend, o se controla solo por el flag global del
server? Hoy es lo segundo. Si prefieren un toggle de UI "imagen real",
lo agrego — es chico. No lo cablée para no imponer costo/latencia de Flux
por defecto.

## 4. Nota de producto (no es del frontend)

Erick observó que algunas preguntas de comprensión no se pueden responder
solo con lo leído hasta esa BANDERA. Es un tema de generación de preguntas
(backend/datos), fuera del alcance del frontend; se registra aquí para que
el dueño de esa pieza lo tenga presente.

## Verificación

`npm run build` estricto + e2e completo (24 checks) en verde contra el stack
aislado (mock :8123 + vite :5199). Los checks del flujo de chat/evaluación
siguen pasando con el textarea (Enter envía).

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`. El `.env` es local/gitignored y de
credenciales — no lo edité; §3 son instrucciones para su dueño.
