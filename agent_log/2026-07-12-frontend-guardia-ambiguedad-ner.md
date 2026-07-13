# Handoff — Guardia interina anti-ambigüedad en el panel NER (bug "Samsa")

**Fecha:** 2026-07-12
**Autor:** agente de Erick (frontend)
**Para:** Giano (backend NER) — **acción de raíz pendiente suya**
**Referencia:** [`2026-07-12-frontend-panel-ner-ventana-movible.md`](2026-07-12-frontend-panel-ner-ventana-movible.md),
[`2026-07-11-backend-evaluacion-ner-panel.md`](2026-07-11-backend-evaluacion-ner-panel.md)

## El bug (confirmado por Giano)

En `chunk_elements` del reader, un mismo apellido aparece a secas y también
en nombres completos distintos. En la_metamorfosis:

| Forma en el JSON | # chunks | Persona |
|---|---|---|
| `Gregorio Samsa` | 88 | el hijo |
| `señor Samsa` | 10 | el padre |
| `Samsa` | 5 | **ambiguo** (¿padre? ¿hijo?) |
| `señora Samsa` | 5 | la madre |
| `Greta` | 13 | la hermana |

`Samsa` a secas cabe en 3 personajes distintos. La de-duplicación anterior
del frontend lo pegaba al primero que lo contenía (`Gregorio Samsa`) y lo
atribuía mal.

## Guardia interina aplicada (frontend)

En `ElementsPanel.tsx`, la canonicalización de variantes ahora es
**consciente de la ambigüedad** (`canonicalize()`):

- fragmento contenido en **0** formas más largas → entidad propia (canónica);
- contenido en **exactamente 1** → se fusiona en ella (variante inequívoca,
  p. ej. `Gregorio` → `Gregorio Samsa`);
- contenido en **2+** → **AMBIGUO: se descarta** (no se muestra ni se
  atribuye).

Resultado: se muestran `Gregorio Samsa`, `señor Samsa`, `señora Samsa`,
`Greta`; `Samsa` a secas desaparece (los tres personajes ya están
representados por su nombre completo). No se inventa ni se adivina a qué
Samsa se refiere — el frontend no tiene contexto para eso.

Verificado e2e (27 checks): se añadió el caso ambiguo al mock y se afirma que
los nombres completos aparecen y que `Samsa`/`Gregorio` sueltos no.

## ⚠️ Arreglo de raíz — para Giano (backend)

Esto es **una curita, no la cura.** El fragmento ambiguo no debería salir del
extractor. Con contexto de la frase, el backend puede:
- **resolver** `Samsa` al personaje correcto en cada chunk, o
- **descartar** el apellido suelto cuando colisiona con varios nombres
  completos (los completos ya cubren a esos personajes).

**Cuando el backend canonicalice, esta guardia y TODA la fusión del frontend
se eliminan** (el panel se alimentaría de una sola fuente de verdad, ya
limpia). Es la secuencia acordada: backend primero, frontend después.

## Qué NO toqué

Solo `frontend/` + `agent_log/`. El bug de raíz es del extractor NER
(backend), territorio de Giano.
