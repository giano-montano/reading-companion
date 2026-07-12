# Handoff — Gate anti scroll-dump, timing del disparo y fuentes numeradas

**Fecha:** 2026-07-12
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo)
**Referencia:** [`2026-07-12-frontend-mock-questions-y-revision.md`](2026-07-12-frontend-mock-questions-y-revision.md)

## Contexto

Pedidos de Erick tras probar contra el backend real con los 8 libros.

## ⚠️ Primero: había DOS servidores en el puerto 8000

Al ponerme al día encontré el backend real (IPv4) y el mock del frontend
(IPv6) escuchando a la vez en :8000 — el navegador resolvía `localhost` al
mock. Si alguien probó "contra el backend real" con el mock encendido, pudo
estar viendo datos del mock sin saberlo. El mock quedó apagado; para e2e
ahora se levanta en otro puerto (`MOCK_PORT=8123` + `VITE_API_BASE_URL`).
Regla práctica: **mock y backend real nunca a la vez en el mismo puerto.**

## Cambios de UX

1. **Gate anti scroll-dump.** El texto se corta en el primer checkpoint con
   pregunta sin resolver: las secciones siguientes (y sus preguntas) no se
   renderizan hasta que el alumno responda en el chat o pulse "Sí, seguir
   leyendo" en el gate ("¿Deseas saltarla y seguir leyendo?"). Saltar baja
   `pending_question` (para no enrutar a evaluación un mensaje normal) y lo
   confirma en el chat. Responder libera el gate automáticamente. Con esto es
   imposible scrollear el libro entero y desplegar las 392 preguntas de golpe.
2. **Timing del disparo.** La pregunta ya no dispara cuando la bandera asoma
   por abajo: la zona de disparo es la franja superior del viewport (35% bajo
   el header), es decir, cuando la sección ya se terminó de leer. Un
   espaciador bajo el gate garantiza que la bandera pueda llegar arriba
   aunque sea el último elemento renderizado.
3. **Fuentes numeradas.** "📖 Fuentes: chunk 3" → "📖 Fuentes: [1] [2]".
   Chips numerados sin la palabra chunk; cada chip navega con scroll suave a
   SU pasaje citado (no solo al primero) y lo deja resaltado.

## Verificado contra el backend real

- `GET /api/books` → 8 libros; `GET .../reader` → BANDERA con `questions[]`
  (marcador crudo en `text`), como documenta el handoff del 2026-07-12.
- `POST /api/images` (`mock:true`) → `202` con `job_id` + poll hasta `done`
  con `image_url`. **El flujo async de imágenes ya estaba implementado en la
  UI (IllustrateBar + rama imagen del chat) y funciona contra el backend
  real tal cual.**

## Verificación automática

E2E rehecho para el flujo con gate (23 checks en verde): texto cortado en el
gate, pregunta no adelantada, disparo casi-arriba, responder libera el gate,
bandera sin pregunta no bloquea ni ensucia el chat, monotonía del progreso,
tooltips, y chips de fuentes (sin "chunk", numerados, navegan al pasaje).
El e2e corre contra un stack aislado (mock :8123 + vite :5199) para no chocar
con el backend real.

## Pendiente / siguiente

- Revisar cambios nuevos en `origin/dev` y sincronizar la rama.
- Deuda de la revisión general sigue vigente (ver handoff anterior).

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`.
