# Handoff — Kickoff del frontend: rama, stack y scaffold

**Fecha:** 2026-07-11
**Autor:** agente de Erick (frontend)
**Para:** equipo (informativo; no requiere acción del backend)
**Referencia:** [`2026-07-10-handoff-frontend-erick.md`](2026-07-10-handoff-frontend-erick.md)

## Contexto

Arranque del frontend según el handoff de Giano del 2026-07-10. Esta sesión
deja la base de trabajo: rama, stack decidido y scaffold compilando.

## Decisiones

1. **Rama `feature/frontend`, creada desde `origin/dev`** (no desde `main`,
   que está 21 commits atrás y no tiene la API). Tracking configurado hacia
   `dev` para sincronizar con `git pull`. Los PR de integración irán contra
   `dev`.
2. **Stack: React 19 + Vite 8 + TypeScript.** Razones: familiaridad de Erick
   con React; la app es una SPA pura que consume la API existente (SSR/Next
   sería sobredimensionar); TypeScript permite tipar el contrato del backend
   (eventos SSE, bloques del reader, estados de jobs de imagen) y detectar
   errores de integración en compilación. Alternativas evaluadas y
   descartadas: Next.js, Vue 3, Svelte.
3. **Todo el frontend vive en `frontend/`** (se reemplazó el placeholder
   `hola.txt`). Nadie más edita esa carpeta; el frontend no edita nada fuera
   de ella salvo `agent_log/` (estos handoffs).

## Qué se hizo

- Scaffold mínimo en `frontend/`: `package.json` (scripts `dev`/`build`/
  `preview`), `tsconfig.json` estricto, `vite.config.ts`, `index.html`,
  `src/main.tsx`, `src/App.tsx` placeholder.
- `src/api/config.ts`: base URL del backend configurable vía
  `VITE_API_BASE_URL` (default `http://localhost:8000`, como indica el
  handoff).
- Verificado: `npm run build` compila sin errores (tsc + vite).

## Hallazgo (informativo, sin acción requerida)

El `.gitignore` raíz ignora `*.json` global (línea 13, pensado para datos del
pipeline), lo que excluía `frontend/tsconfig.json` y
`frontend/package-lock.json`. **No se tocó el `.gitignore` raíz** (archivo
compartido): se resolvió con una negación `!*.json` en `frontend/.gitignore`,
que solo aplica dentro de `frontend/`. Si el equipo prefiere otra solución
(p. ej. acotar la regla raíz a `data/**/*.json`), es cosa suya; lo actual
funciona.

## Próximos pasos (frontend)

1. Tipar el contrato de la API en `src/api/` (bloques del reader, eventos SSE
   del chat, jobs de imagen) según el handoff del 2026-07-10.
2. Catálogo (`GET /api/books`) y vista de lectura (`GET /api/books/{id}/reader`)
   con tracking de scroll → `focus_chunk_ids` / `max_progress_chunk_index`.
3. Chat SSE (`fetch` + `getReader()`, mañas #1–#3) y botones de imagen con
   `mock: true` para maquetar.

## Qué NO toqué

Nada fuera de `frontend/` y `agent_log/`. Sin cambios en backend, contratos
ni datos.
