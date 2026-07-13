# Handoff — Mensaje amable cuando el anti-spoiler bloquea la respuesta + integración de dev

**Fecha:** 2026-07-13
**Autor:** agente de Erick (frontend)
**Para:** equipo — §"Petición al backend" es para Chang/Giano.
**Referencia:** diagnóstico del bug de retrieval (conversación 2026-07-12/13),
[`2026-07-12-frontend-panel-ner-ventana-movible.md`](2026-07-12-frontend-panel-ner-ventana-movible.md)

## Contexto

Usuarios reportaron que al preguntar sobre el chunk 1 (recién empezando) el
chat respondía "No tengo suficiente contexto en esta parte de la obra para
responder eso". Causa raíz (backend, ya notificada): el QA-RAG hace
"retrieve-then-filter" — recupera top_k=5 de TODA la obra y luego el
anti-spoiler descarta los de índice > progreso; al inicio suele descartarlos
todos (`orchestrator.py`, rama `if not filtered`). El fix de raíz es del
backend (filtrar en la query de Chroma). Esto es la mejora de UX **mientras**.

## Cambio de frontend (interino)

Cuando el QA-RAG no responde **porque el anti-spoiler filtró todo**, el chat
muestra un mensaje amable con intención pedagógica en vez del técnico:

> "Sigue leyendo y lo descubrirás… ¡no quiero hacerte spoiler! 📖"

**Solo** en ese caso. El otro "sin resultados" (retrieval vacío, "no encontré
fragmentos relevantes") se deja tal cual.

### Cómo se detecta (y por qué es frágil)

El backend NO manda una señal distinta: ambos "no answer" llegan como
`citations {answered:false, citations:[]}`. Lo único que los diferencia es el
texto. Detectamos por la subcadena distintiva **"suficiente contexto"** (única
de la rama anti-spoiler) y reemplazamos el texto de la burbuja.

- Acoplamiento frágil **a propósito**: si el backend cambia el texto,
  degradamos a mostrar el mensaje original (no rompe nada).
- Hay un parpadeo breve: el texto técnico llega por tokens y se reemplaza al
  llegar `citations`. Con el streaming simulado del backend real es rápido.

### 🙏 Petición al backend (fix robusto, opcional)

Si en `citations` (o un evento nuevo) mandan un campo que distinga el motivo
—p. ej. `reason: "anti_spoiler" | "no_results"`— quito el match por texto y
esto deja de ser frágil. El mensaje amable tiene valor permanente: siempre
habrá preguntas legítimamente bloqueadas (p. ej. "¿quién muere al final?"
estando en el capítulo 1).

## Integración de dev (7 commits nuevos)

Fast-forward de `origin/dev` a `feature/frontend` (0 conflictos). Incluye
mejoras de backend (visual/prompts, `scene_planner.py`) y **una edición del
equipo a `frontend/src/api/client.ts`**: header `ngrok-skip-browser-warning`
en los fetch (para exponer el backend por ngrok en la demo). Es sensato, lo
acepté tal cual. Nota de propiedad: `frontend/` es nuestro; para próximas
veces, mejor que nos lo pidan por handoff, pero este cambio no genera
fricción.

### Bug destapado por ese header

El header extra dispara **preflight CORS**. El backend real ya usa
`allow_headers=["*"]`, pero **el mock** solo permitía `Content-Type` → el
navegador bloqueaba todas las peticiones contra el mock. Alineado el mock a
`Access-Control-Allow-Headers: *`.

## Verificación

`npm run build` + e2e (nuevo check: preguntar por el final → mensaje amable,
sin el texto técnico). Todo en verde.

## Qué NO toqué

Solo `frontend/` + `agent_log/`. El fix de raíz del retrieval es del backend.
