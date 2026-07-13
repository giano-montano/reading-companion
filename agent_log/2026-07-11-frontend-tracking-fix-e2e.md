# Handoff — Bug del tracking congelado (StrictMode) + verificación e2e con Playwright

**Fecha:** 2026-07-11
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo)
**Referencia:** [`2026-07-11-frontend-reader-tracking-mock.md`](2026-07-11-frontend-reader-tracking-mock.md)

## Contexto

Erick reportó en pruebas manuales que la barra de estado mostraba
"viendo: 1, 2" mientras en pantalla estaban los chunks 4–6. Era un bug real.

## Causa raíz

En desarrollo React corre con `StrictMode`, que simula un desmontaje/remontaje
del componente. El cleanup del `useReadingTracker` desconectaba el
`IntersectionObserver` y vaciaba los registros, pero los ref callbacks de los
bloques no vuelven a ejecutarse en el remontaje → nada se re-observaba y el
tracking quedaba congelado en el último valor. Se "descongelaba" parcialmente
cuando algo re-renderizaba los bloques (p. ej. al llegar citations), lo que
explicaba los valores inconsistentes.

## Arreglo y calibración

- El `useEffect` ahora es dueño del ciclo de vida del observer: lo crea,
  **re-observa todo lo ya registrado** y lo destruye. Los refs solo registran.
- Calibración de la zona visible: se descuentan el header sticky
  (`TOP_OFFSET = 64`) y la barra de estado (`BOTTOM_OFFSET = 40`) vía
  `rootMargin`; un bloque tapado por el header ya no cuenta como visible, y
  "dejado atrás" = borde inferior por encima del header.

## Verificación e2e (nuevo)

`npm run e2e:tracking` (Playwright + Chromium, nueva dev-dependency): abre la
app real, entra al libro y en varios puntos de scroll compara la barra de
estado contra la verdad medida con `getBoundingClientRect` sobre los bloques
(`data-chunk` nuevo en el DOM). Verifica también la monotonía del progreso al
volver arriba y los tooltips. 13 verificaciones en verde contra el dev server
con StrictMode (el entorno del bug). Requiere `npm run mock` + `npm run dev`
corriendo.

## También en este cambio

- Tooltips en los 4 botones de ilustrar (petición de Erick; los scopes no se
  explicaban solos): "lo que veo" = pantalla actual, "esta sección" =
  capítulo, "hasta aquí" = todo lo leído, "toda la obra" = libro completo con
  aviso de spoiler.

## Aclaraciones de producto (para quien pruebe la UI)

1. Los prefijos "(5.2)" en los párrafos son **solo del texto sintético del
   mock** (numeran chunk.párrafo para poder calibrar a ojo); los libros
   reales no los tendrán.
2. La pregunta de comprensión en las BANDERA depende de la tool EVALUACIÓN
   del backend (aún no implementada). El frontend marcará la pausa y cableará
   la interacción cuando el contrato exista (handoff 2026-07-10 §8 pide no
   anticipar su forma).

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`.
