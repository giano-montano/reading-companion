# Plan de mejora del NER (personajes y lugares) — hacia producto final

**Fecha:** 2026-07-12
**Autor:** agente de Giano (backend)
**Insumo:** [`ner-deep-research-report.md`](ner-deep-research-report.md) (investigación previa de Giano) + diagnóstico empírico sobre el corpus real.

Este documento aterriza la investigación previa en la realidad de **nuestro** corpus
y código, y propone un plan por fases. La conclusión corta: **el modelo NER no es
el cuello de botella; el post-procesamiento sí.** Cambiar de spaCy a un modelo más
grande sube ~1 punto de F1 (89→90) y no arregla ninguno de nuestros tres problemas
reales.

---

## 1. Diagnóstico empírico (no teoría — medido sobre `la_metamorfosis`)

Salida actual del extractor (96 chunks, spaCy `es_core_news_md` + filtros léxicos):

- **Personajes únicos: 10.** Buenos: `Gregorio` (87), `Greta` (13), `Samsa` (11),
  `señor Samsa` (5). **Basura que se cuela:** `señor` (4), `Quería` (2), `Estoy` (2),
  `Había` (2), `Temía` (2), `Gregori` (2, truncado).
- **Lugares únicos: 1** → `Charlottenstrasse` (2). Nada más.

### Causa raíz de cada síntoma

| Síntoma | Causa real | ¿Modelo más grande lo arregla? |
|---|---|---|
| `Quería`, `Estoy`, `Había`, `Temía` como personajes | Verbos al **inicio de oración** que spaCy etiqueta PER/LOC. Mi filtro de sufijos verbales excluía `-ía` a propósito (para salvar *María/Adrián*), así que `Quería/Había/Temía` pasan. | ❌ No. Es un error de spans, no de vocabulario. |
| `Samsa entró` (span inflado) | spaCy a veces mete el verbo dentro de la entidad. | ❌ No. |
| **No detecta lugares** | *La Metamorfosis* es una novela **doméstica**: casi no hay topónimos propios. Los "lugares" que importan son **sustantivos comunes**: `habitación` (150 ocurrencias), `cuarto` (22), `cocina` (14), `calle` (11), `sala` (4). NER **por diseño** no captura sustantivos comunes. | ❌ No. NER busca nombres propios; aquí no los hay. |
| `Gregorio` separado de `Gregorio Samsa`, nunca el nombre completo | En el libro `Gregorio Samsa` (bigrama) aparece casi solo en la frase inicial. El resto es `Gregorio`. Y `Samsa` es el **apellido familiar** (padre = *señor Samsa*, madre = *señora Samsa*). No es un bug: es que **falta agrupar alias** y elegir una forma canónica. | ❌ No. Es coreferencia/normalización. |
| `señor` suelto | Honorífico que quedó huérfano de su apellido. | ❌ No. Normalización. |

### El hallazgo que ordena todo el plan

Corrí una prueba de POS (part-of-speech) token por token:

```
'Había verduras podridas.'      -> [('Había', PER, root=AUX)]     ← verbo
'Vivían en la Charlottenstrasse'-> [('Vivían', LOC, root=VERB),   ← verbo
                                    ('Charlottenstrasse', LOC, root=PROPN)]  ← real
'Gregorio Samsa despertó.'      -> [('Gregorio Samsa', PER, root=PROPN)]     ← real
'El señor Samsa entró.'         -> [('Samsa entró', MISC, root=VERB)]        ← span inflado
```

**spaCy ya sabe la respuesta y la estamos tirando a la basura.** El provider
(`spacy_ner.py`) solo devuelve `text/label/span`; descarta el POS de cada token.
Si en cambio **filtramos los tokens de la entidad para quedarnos solo con los
`PROPN`**:
- `Había`, `Vivían`, `Quería`, `Estoy`, `Temía` → eliminados (raíz VERB/AUX).
- `Samsa entró` → recortado a `Samsa`.
- `Gregorio Samsa`, `Charlottenstrasse` → intactos.

Esto es **una sola librería (spaCy), sin LLM, sin modelo nuevo**, y mata la mayor
parte de la basura. Es la intervención de mayor retorno y la base de la Fase 1.

---

## 2. Qué de la investigación previa aplica y qué no

La investigación de Giano es sólida y coincide en lo esencial (spaCy/Stanza/Flair
~88–91 F1; el trabajo real está en post-proceso y coreferencia). Ajustes con
nuestra realidad:

- ✅ **Post-procesamiento + reglas > modelo más grande.** Confirmado empíricamente.
- ✅ **No hay coref maduro en español.** Correcto → vamos con heurísticas de
  agrupación por apellido/honorífico (no pronombres, ver abajo).
- ⚠️ **Correferencia de pronombres (él/ella → antecedente):** el reporte la
  propone, pero para **nuestro** propósito (listar personajes/lugares por chunk)
  **no aporta** y es frágil. No resolvemos pronombres; solo agrupamos alias de
  nombres propios. Bajaría precisión sin subir la utilidad del panel.
- ⚠️ **Stanza/Flair/BETO:** el reporte los lista, pero ninguno está en
  `pyproject.toml` (solo `spacy` como extra opcional). Flair/BETO piden GPU;
  probablemente no la hay en las máquinas del equipo. Los dejo como **Fase 3
  opcional** y solo si medimos que el recall lo justifica.
- ❌ **El gran vacío del reporte:** asume que "lugares" = topónimos (NER LOC). Para
  media biblioteca (La Metamorfosis, novelas domésticas) **eso da ~0**. El reporte
  no aborda lugares-como-sustantivo-común. Es la decisión de producto más
  importante (§4).

---

## 3. Arquitectura propuesta (por fases)

El módulo `narrative_elements.py` ya tiene la forma correcta (2 pasadas:
recolectar por chunk → resolver a nivel libro). Se mantiene; cambia el interior.

### Fase 1 — Precisión de personajes con POS (sin dependencias nuevas) ⭐ prioridad

1. **Enriquecer el provider.** `spacy_ner.py` debe exponer, por entidad, el POS de
   sus tokens (o al menos: lista de tokens `PROPN`). Ampliar el `TypedDict Entity`
   con un campo opcional (p. ej. `propn_text: str`) sin romper el contrato actual.
2. **Filtro POS token-level** en `_clean`/recolección: quedarse solo con tokens
   `PROPN` (y `PROPN`+partícula tipo *de/von*). Esto reemplaza el frágil blacklist
   de sufijos verbales. Recorta spans inflados y elimina verbos-inicio-de-oración.
3. **Mantener** el gate de recurrencia (≥2 en el libro) y las etiquetas nativas
   PER→personajes / LOC→lugares (decisión 2026-07-12).
4. **Resultado esperado en La Metamorfosis:** personajes ≈ `{Gregorio (Samsa),
   Greta, Samsa, señor Samsa, señora Samsa}` sin `Quería/Había/Estoy/Temía/señor`.

### Fase 2 — Normalización y alias (responde "nunca muestra Gregorio Samsa")

Heurísticas léxicas, sin LLM (lo que el reporte llama coref, versión pragmática):

1. **Fusión de honoríficos:** `señor/señora/don/doña + Apellido` → una entidad
   (`señor Samsa`), y `señor` suelto se descarta o se ata al apellido más cercano.
2. **Clustering por apellido/subcadena a nivel libro:** `Gregorio` ⊂
   `Gregorio Samsa` → mismo cluster; se muestra la **forma canónica** (la más
   informativa/larga) una vez. Cuidado: `Samsa` sola NO se absorbe en `Gregorio
   Samsa` porque es el apellido de toda la familia → se mantiene distinción
   padre/madre. (Esto ya existe a medias en el frontend `ElementsPanel`; conviene
   moverlo al backend para que sea canónico y no se reinvente por cliente.)
3. **Corregir truncados** (`Gregori`) por coincidencia de prefijo con una forma
   más larga del mismo cluster.

### Fase 3 — Lugares: solo topónimos propios ✅ (decidido 2026-07-12: opción A)

**Decisión de Giano:** lugares = **solo nombres propios de lugar** vía NER LOC +
filtro PROPN. **No** habrá extractor de sustantivos comunes ("escenarios").

- Cae casi gratis de la Fase 1 (mismo filtro PROPN aplicado a etiquetas LOC).
- Funciona bien en *Oz, Viaje al centro de la Tierra, Crónica* (sí tienen
  topónimos). En *La Metamorfosis* mostrará poco (`Charlottenstrasse`) — y **está
  bien**: es honesto con un libro que no tiene lugares nombrados.
- Descartada la vía "escenarios" (sustantivos de lugar recurrentes). Si en el
  futuro se quiere, queda documentada abajo como idea muerta:
  > ~~Extraer `la habitación`, `la cocina` vía POS `NOUN` + lista curada,
  > filtrada por frecuencia, como categoría "escenarios".~~ (no se hace)

### Fase 4 — Evaluación (para poder decir "es de producto")

Sin medición no hay producto. Barato y suficiente:
1. **Gold set pequeño:** anotar a mano personajes/lugares de ~15–20 chunks de 2–3
   libros distintos (uno doméstico, uno de viajes). ~1–2 h de trabajo.
2. **Métricas P/R/F1 a nivel mención** con un script propio (no hace falta
   `seqeval`; comparación de conjuntos por chunk basta para el panel).
3. **Casos difíciles** del reporte (honoríficos, apellido suelto, topónimo
   compuesto) como tests de regresión.
4. Meta realista: **precisión alta > recall** (para un panel estudiantil, mejor
   mostrar 5 personajes correctos que 12 con basura — tu propia guía del 2026-07-12).

---

## 4. Decisiones

1. **Lugares en novelas domésticas:** ✅ **DECIDIDO — opción (A) solo topónimos
   propios.** Sin extractor de escenarios/sustantivos comunes. La Metamorfosis
   quedará casi vacía en lugares y es aceptable.
2. **¿Fase 3 opcional (modelo transformer para recall)?** Solo si tras medir (Fase
   4) el recall de personajes en algún libro es malo. Cuesta añadir `torch` (CPU
   lento pero 96 chunks es viable). Por defecto **no**, salvo que la medición lo pida.
3. **¿Mover el clustering de alias del frontend al backend?** Recomiendo sí (una
   sola fuente de verdad, canónica). Erick tendría que quitar su merge del panel.

---

## 5. Esfuerzo estimado

| Fase | Alcance | Esfuerzo | Dependencias nuevas |
|---|---|---|---|
| 1 — POS personajes | Provider + `_clean` | ~medio día | ninguna |
| 2 — Alias/honoríficos | `narrative_elements.py` | ~medio día | ninguna |
| 3a — Topónimos | ya cae de Fase 1 | ~1 h | ninguna |
| 3b — Escenarios | lista curada + POS NOUN | ~medio día | ninguna |
| 4 — Evaluación | gold set + script métricas | ~1 día (incluye anotar) | ninguna |
| 3 opcional — transformer | `es_dep_news_trf`/HF | ~1 día | `torch` |

**Camino recomendado:** Fase 1 → 2 → 3a → 4, todo con spaCy y cero dependencias
nuevas. Decidir 3b según tu respuesta al punto 1. La Fase 3-transformer solo si la
evaluación la justifica.

---

## Archivos que tocaría (referencia, aún NO implementado)

- `src/companion/providers/ner_base.py` — `Entity` con POS/propn opcional.
- `src/companion/providers/spacy_ner.py` — exponer POS de tokens.
- `src/companion/analysis/narrative_elements.py` — filtro POS + alias/honoríficos.
- `scripts/extract_narrative_elements.py` — sin cambios de interfaz.
- (nuevo) `data/eval/ner_gold/*.json` + `scripts/eval_ner.py` — Fase 4.
- `frontend/src/components/ElementsPanel.tsx` — si movemos el merge al backend.