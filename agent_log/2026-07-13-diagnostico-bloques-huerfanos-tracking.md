# Diagnóstico — bloques gigantes y chunks huérfanos rompen el tracking de lectura

**Fecha:** 2026-07-13
**Autor:** agente de Giano
**Para:** Chang + su agente (dueños de `src/preprocesamiento/`)
**Estado:** diagnóstico, **sin implementar**. La decisión de tocar el pipeline es de Chang.

---

## 1. Resumen ejecutivo

El contador "leído hasta el chunk N" del frontend **salta a trompicones** (de 5 a 13
con un scroll leve) en *El maravilloso Mago de Oz*. No es un bug del frontend: es un
**defecto de los datos** que nace en `build_master.py`.

En Oz, **132 de 156 chunks son huérfanos**: ningún bloque del reader los apunta, así
que el tracker no puede reportarlos jamás. **Solo el 15% del libro es visible para el
tracking.** El problema existe en 7 de los 8 libros, con distinta gravedad.

Afecta a más cosas que al contador (ver §5): el foco del RAG, las citas y el
anti-spoiler.

---

## 2. Síntoma

`useReadingTracker.ts` calcula `max_progress_chunk_index` leyendo el `chunk_id` de los
bloques que entran/salen del viewport. En Oz el valor salta:

```
1 → 5 → 13 → 21 → 26 → 35 → 41 → 48 → 55 …
```

Se pierde toda granularidad intermedia. El alumno lee durante minutos y el progreso no
se mueve; luego pega un brinco de 8 chunks de golpe.

---

## 3. Causa raíz

### 3.1 El EPUB de Oz (generado por Calibre) mete un capítulo entero en un solo `<p>`

Los párrafos van marcados como `<span>…</span><br/>` **dentro** de un único
`<p class="calibre">` por capítulo:

```html
<p class="calibre">
  <span>Cuando Dorothy se detenía en el vano de la puerta…</span><br class="calibre1"/>
  <span>Cuando la tía Em fue a vivir allí…</span><br class="calibre1"/>
  <span>Tampoco reía nunca el tío Henry…</span><br class="calibre1"/>
  …19 spans, 18 br…
</p>
```

`build_master.py::extract_blocks_from_epub` solo mira `{h1,h2,h3,p}` y hace
`element.get_text(" ", strip=True)`, que **aplasta los `<br>` en un espacio**. El
capítulo entero sale como **un bloque de 18.446 caracteres** (un chunk son ~1.700).

Recuento de tags en el EPUB de Oz: `br: 1186, span: 1180, div: 73, p: 71, h1: 25, h2: 25`.
Es decir: 71 `<p>` para todo el libro, y 1.186 párrafos reales escondidos tras los `<br>`.

### 3.2 Un bloque solo puede llevar UN chunk_id

`generate_chunks.py` (líneas ~312-333) asigna a cada bloque el **primer** chunk que lo
contiene; si el bloque no cabe en ningún chunk, cae al fallback: el chunk donde
**empieza** el bloque.

Combinado con 3.1: el bloque-capítulo abarca los chunks 5..12 pero se marca como
chunk **5**. El siguiente bloque ya arranca en el chunk **13**. **Los chunks 6-12 no
son apuntados por ningún bloque** → el tracker no puede emitirlos nunca.

---

## 4. Alcance en el catálogo

Auditoría sobre `data/master/*.master.json` (script reproducible en §9):

| libro | chunks | bloques narr. | **huérfanos** | alcanzable | bloque máx (chars) | salto máx |
|---|---|---|---|---|---|---|
| el_maravilloso_mago_de_oz | 156 | 72 | **132** | **15%** | **18.446** | 15 |
| la_ciudad_y_los_perros | 675 | 2795 | 202 | 70% | **17.067** | 14 |
| cronica_de_una_muerte | 137 | 298 | 31 | 77% | 3.818 | 3 |
| la_metamorfosis_franz_kafka | 96 | 196 | 14 | 85% | 4.400 | 4 |
| las_aventuras_de_tom_sawyer | 382 | 1839 | 40 | 89% | 4.059 | 3 |
| el_viejo_y_el_mar | 139 | 660 | 2 | 98% | 1.264 | 2 |
| viaje_al_centro_de_la_tierra | 414 | 2306 | 1 | 99% | 1.491 | 2 |
| matalache | 354 | 4497 | **0** | **100%** | 175 | 1 |

**Matalaché es el control**: párrafos normales (máx 175 chars), cero huérfanos, contador
perfecto. La correlación es directa: *bloque más grande que un chunk → chunks huérfanos*.

---

## 5. El daño no se limita al contador

1. **Foco del RAG erróneo.** `focus_chunk_ids` ("lo que el alumno ve ahora") se queda
   **congelado en el chunk 5 durante todo el capítulo**, aunque el alumno esté leyendo
   el texto del chunk 11. El agente recibe un contexto de foco que no corresponde a lo
   que hay en pantalla.
2. **Citas que no resaltan.** `ReaderView.isCited()` empareja por `chunk_id`. Si el
   agente cita un chunk huérfano (y en Oz el 85% lo son), **ningún bloque se resalta**.
3. **Anti-spoiler descalibrado.** Mientras se lee el capítulo es demasiado restrictivo
   (progreso congelado); al pasarlo, salta 8 chunks de golpe.
4. **Naturalidad de las preguntas** (la queja original de Giano): el sistema no reconoce
   que ya se leyeron los chunks intermedios.

---

## 6. Son DOS causas distintas, no una

Simulé el arreglo de partir por `<br>` sobre los 8 EPUBs (§9 trae el script):

| libro | bloques antes → después | bloque máx antes → después | bloques > 1.700 chars |
|---|---|---|---|
| Mago de Oz | 74 → **1.205** | 18.446 → **1.212** | **0** ✅ |
| Viaje al centro de la Tierra | 2.358 → 6.897 | 1.491 → 255 | 0 |
| Tom Sawyer | 1.857 → 1.883 | 4.059 → 4.059 | 23 |
| El viejo y el mar | 674 → 675 | 1.264 → 1.264 | 0 |
| **La ciudad y los perros** | 2.806 → **2.806** | 17.067 → **17.067** | **74** ❌ |
| **La metamorfosis** | 198 → 198 | 4.400 → **4.400** | 10 ❌ |
| **Crónica de una muerte** | 306 → 306 | 3.818 → **3.818** | 15 ❌ |
| Matalaché | 4.532 → 4.532 | 175 → 175 | 0 |

**Causa A — el `<br>` de Calibre.** Solo afecta a Oz (y a Viaje, que ya estaba al 99%).
Partir por `<br>` deja Oz **perfecto**: máximo 1.212 chars, ningún bloque más grande que
un chunk.

**Causa B — párrafos legítimamente más largos que un chunk.** *La ciudad y los perros*
(17k chars: flujo de conciencia de Vargas Llosa), Kafka (4.4k), Crónica (3.8k). Aquí no
hay `<br>` que partir: **son párrafos reales enormes**. El fix A no los toca. Necesitan
partirse por frase hasta caber en un chunk (~1.700 chars).

> ⚠️ **Ojo con Viaje al centro de la Tierra**: el split por `<br>` lo fragmenta de 2.358 a
> 6.897 bloques (máx 255 chars) porque usa `<br>` como salto de línea *dentro* de
> párrafos, no como frontera. Ya está al 99% de alcance, así que no gana nada y cambia su
> maquetación. **Sugerencia: aplicar el split por `<br>` solo a los `<p>` que superen un
> umbral (p. ej. 1.500 chars).** Ningún `<p>` de Viaje llega a 1.500 (su máx es 1.491),
> así que ese guardarraíl lo deja intacto y arregla Oz igual.

---

## 7. Un atajo que NO funciona (para que nadie pierda tiempo)

Se evaluó añadir un campo derivado `chunk_id_end` al reader (el último chunk que solapa
el bloque), usándolo para el "dejado atrás". **Atractivo porque tiene coste cero: no
cambia `id_block`, no invalida banderas, ni Chroma, ni preguntas — solo re-generar el
`.reader.json`.**

**No resuelve el problema.** El bloque-capítulo sigue siendo **atómico para el
IntersectionObserver**: mientras el alumno lo lee no hay ningún evento intermedio que
disparar. El contador seguiría saltando de 5 a 13 igual, y el foco seguiría congelado.

**Conclusión: para Oz no hay atajo. Hay que partir el bloque en el master.**

(`chunk_id_end` sigue siendo un complemento razonable *después* del fix, para bloques que
aun así crucen una frontera de chunk. Pero no sustituye nada.)

---

## 8. Opciones y coste

Cualquier fix toca `build_master.py` → **cambian todos los `id_block`** → invalida aguas
abajo, en este orden:

```
build_master.py          ← el fix va aquí
   ↓
classify_narrative.py    re-clasificar (¿coste LLM?)
   ↓
insert_banderas.py       las banderas están ancladas a id_block → se reinsertan
   ↓
generate_chunks.py       re-chunkear (cambian los chunks y sus ids)
   ↓
add_questions_to_banderas.py   ⚠️ COSTE LLM — regenerar preguntas de checkpoint
   ↓
build_reader_and_retrieval.py
   ↓
chunk_summaries.py       ⚠️ COSTE LLM — regenerar resúmenes de chunk
   ↓
index_to_chroma.py       re-indexar (~90 MB)
   ↓
scripts/extract_narrative_elements.py   re-correr NER
```

| Opción | Qué arregla | Coste |
|---|---|---|
| **A** — partir por `<br>` los `<p>` grandes | Oz: 15% → ~100% | Pipeline completo. Quirúrgico en código; no toca la maquetación de los otros libros si se usa el umbral de §6. |
| **B** — partir por frase los párrafos > tamaño de chunk | La ciudad y los perros, Kafka, Crónica, Tom Sawyer | Mismo pipeline. Efecto secundario: un párrafo de 17k se renderiza como varios párrafos en el reader. |
| **A + B** en una sola pasada | Todo el catálogo | **Recomendado**: el re-pipeline es el coste dominante y sería absurdo pagarlo dos veces. |
| No hacer nada | — | El tracking de Oz seguirá siendo inservible y el foco del RAG, erróneo. |

**Recomendación: A + B juntos**, y validar primero **solo con Oz** (regenerar un único
master) antes de tocar los otros 7 libros — menos riesgo y menos gasto de LLM.

---

## 9. Cómo reproducir (auditoría)

**Auditoría del estado actual** — cuenta huérfanos por libro:

```python
# python - <<'PY'   (desde la raíz del repo)
import json, glob, os
def idx(c):
    if isinstance(c, int): return c
    if isinstance(c, str) and "::chunk::" in c: return int(c.split("::chunk::")[1])
    return 0
for fp in sorted(glob.glob("data/master/*.master.json")):
    d = json.load(open(fp, encoding="utf-8"))
    ch = d.get("chunks") or []
    if not ch: continue
    narr = [b for b in d["blocks"] if b["is_narrative"] and b.get("type") != "BANDERA"]
    seq = [idx(b["chunk_id"]) for b in narr]
    used = set(seq)
    jumps = [seq[i+1] - seq[i] for i in range(len(seq)-1)] or [0]
    n = os.path.basename(fp).replace(".master.json", "")[:40]
    print(f"{n:<42}{len(ch):>7}{len(narr):>7}  huerfanos={len(ch)-len(used):<5}"
          f"alcanz={len(used)*100//len(ch):>3}%  maxblq={max(len(b['text']) for b in narr):>6}"
          f"  saltoMax={max(jumps)}")
PY
```

**Criterio de aceptación del fix** (medible, sin abrir el navegador):

- `huerfanos == 0` y `saltoMax == 1` para **todos** los libros.
- `maxblq` por debajo del tamaño típico de chunk (~1.700 chars).
- Matalaché ya cumple hoy: sirve de referencia de "cómo se ve bien".

---

## 10. Contratos que NO deben cambiar

1. Texto canónico: `"\n\n".join(block.text)` de los bloques narrativos, en orden.
2. `char_start`/`char_end` = offsets absolutos sobre ese texto canónico.
3. `chunk_id` en el reader sigue siendo `string` (`libro::chunk::N`) o `null`.
   **El frontend depende de este formato** (`chunkIndexOf()` parsea `::chunk::N`).
4. Las `BANDERA` siguen con `is_narrative=false`, `chunk_id=null`, `char_start=-1`.

Si el fix se aplica, el frontend (Erick) **no necesita cambios**: el tracker ya funciona
bien; simplemente hoy recibe datos con los que es imposible acertar.
