# Handoff — reconciliar Scope / anti-spoiler: `section` (Giano) vs `chunk_id` (Chang)

**Fecha:** 2026-07-07
**Autor:** Giano (con agente)
**Para:** Chang + su agente de terminal
**Depende de:** [`2026-07-05-contratos-scope-router.md`](2026-07-05-contratos-scope-router.md),
[`2026-07-05-preprocessing-pipeline.md`](2026-07-05-preprocessing-pipeline.md)

## Por qué existe este doc

Al integrar tu pipeline con mi capa de agente aparece una **colisión de contrato
real** en el eje del anti-spoiler y del scope. No es un bug de código: es que
diseñamos "progreso de lectura" con dos unidades distintas. Hay que elegir UNA
antes de cablear las tools (QA-RAG/RESUMIR/EVALUACIÓN), o construimos sobre
arena. Este doc explica mi modelo mental, **mi recomendación**, y las
sub-decisiones que **decidimos tú (Chang) y yo juntos**. Al final hay un prompt
listo para pasarle a tu agente.

## Los dos modelos, lado a lado

| | **Mi diseño (contracts + ScopeResolver)** | **Tu diseño (master + preprocessing)** |
|---|---|---|
| Unidad del chunk | `ChunkRef.section: int` (una sección por chunk) | `BookChunk.section_ids: list[int]` (cruza secciones) |
| Eje de progreso (C) | `max_progress_section: int` | `chunk_id` (y `block_id` dentro del chunk actual) |
| Anti-spoiler | `section <= C` (`ScopeResolver.up_to`) | por `chunk_id` (ver `book_master.py:48`) |
| Secciones | siempre presentes, obligatorias | **manuales**; por defecto `sections: []` |
| Granularidad | sección (gruesa) | chunk / bloque (fina) |

## Mi modelo mental y hacia dónde creo que va

**Recomiendo adoptar tu eje: el progreso y el anti-spoiler se miden por
`chunk_id` (int, autoincremental en orden de lectura), NO por sección.** Razones,
en orden de peso:

1. **Las secciones son opcionales y suelen estar vacías.** No se puede *gatear*
   sobre datos que la mayoría de los libros no tendrán (`sections: []`). El
   `chunk_id` siempre existe.
2. **`chunk_id` es monótono en orden de lectura** (lo asignas incremental). Es un
   *high-water mark* perfecto: `max_progress_chunk_id` solo sube.
3. **Ya está implementado así** en tu pipeline y es más fino (protección a nivel
   párrafo vía `block_id`), mejor UX pedagógica.
4. Las secciones **no desaparecen**: siguen siendo el eje de las *pausas
   pedagógicas* y del modo de scope "resúmeme esta sección". Solo dejan de ser el
   eje del anti-spoiler.

En una frase: **el anti-spoiler es por `chunk_id`; las secciones son para
navegación/pausas, no para censura.**

## Propuesta concreta de contrato reconciliado

Esto es lo que yo cambiaría en **mi** lado (`contracts.py`, `resolver.py`) si
estás de acuerdo. Nombres a discutir; la forma es lo importante.

### `ReadingState` (en `agent/tools/contracts.py`)
```python
class ReadingState(BaseModel):
    focus_chunk_ids: list[int]          # A) chunks (por id) que intersectan el viewport
    max_progress_chunk_id: int          # C) high-water mark; monótono. EJE ANTI-SPOILER
    current_block_id: int | None = None # revelado parcial del chunk actual (tu regla de bloque)
    last_completed_section: int | None = None  # B) solo-UI/pausas; NO gatea nada
```
- **Cambio clave:** `max_progress_section` → **`max_progress_chunk_id`**.
- `current_block_id` opcional: si viene, el chunk actual se revela solo hasta ese
  bloque (tu semántica de `book_master.py`). Si no, el gate es a nivel chunk.

### `ScopeChunk` / `ChunkRef`
```python
# ChunkRef (catálogo runtime, hoy en resolver.py)
chunk_id: int                  # ordinal del master — ORDEN + GATE
section_ids: list[int]         # reemplaza `section: int`
char_start: int; char_end: int # sobre el texto canónico (inclusive/exclusive)
chroma_id: str                 # identidad de recuperación: f"{book_id}::chunk_{i}::text"
```

### `ScopeResolver` (modos)
- `hasta_aqui` → `chunk.chunk_id <= max_progress_chunk_id` (antes `section <= C`).
- `seccion(section_id)` → `section_id in chunk.section_ids` (membresía, no igualdad).
- `lo_que_veo` (offset overlap) y `obra` → sin cambios.
- **(opcional)** revelado parcial del chunk actual hasta `current_block_id`.

## Sub-decisiones que tenemos que cerrar tú y yo

1. **Doble identidad de id.** El master usa `chunk_id: int` (1,2,3…) pero Chroma
   usa `str` (`{book_id}::chunk_{i}::text`). Mi propuesta: el catálogo runtime
   carga **ambos** — `chunk_id: int` (orden/gate) + `chroma_id: str`
   (recuperación); y las `Citation` al frontend usan el **int** + offsets, porque
   tu `reader.json` referencia bloques con `chunk_id: int`. ¿De acuerdo? ¿O
   prefieres un solo id string en runtime?

2. **Revelado parcial por bloque** del chunk actual: ¿lo metemos ya, o gate a
   nivel chunk primero (más simple, desbloquea QA-RAG) y bloque como v2? Mi rec:
   chunk primero, bloque después — salvo que tu anti-spoiler ya dependa del
   bloque en el MVP.

3. **El catálogo/manifiesto runtime.** `jobs/index_book.py` está vacío. Alguien
   debe derivar del master la lista `[{chunk_id, section_ids, char_start,
   char_end, chroma_id}]` que consume mi `ScopeResolver` (y embeber el
   `retrieval.jsonl` en Chroma). **Propongo que ese job sea tuyo** (naces del
   master, que es tu fuente de verdad); yo consumo su salida. ¿Ok?

4. **Secciones como eje de scope** (no de anti-spoiler): confirmamos que
   `seccion`/"resume esta sección" siguen existiendo por membresía en
   `section_ids`, aunque muchos libros tengan `sections: []`. ¿De acuerdo?

5. **B (`last_completed_section`)**: ¿lo mantengo como dato solo-UI (barra de
   progreso/pausas) o lo elimino del contrato por ahora? Mi rec: mantener,
   opcional, sin gatear.

## Reparto de implementación (una vez cerrado el contrato)

- **Giano (yo):** cambio `agent/tools/contracts.py` (`ReadingState`, `ScopeChunk`)
  y `scope/resolver.py` (`ChunkRef`, modos `hasta_aqui`/`seccion`). NO toco tu
  pipeline.
- **Chang:** `jobs/index_book.py` — emitir el catálogo runtime desde el master +
  indexar `retrieval.jsonl` en Chroma con el `chroma_id` y `char_start/char_end`
  en metadata. Confirmar la semántica exacta del anti-spoiler por chunk/bloque.
- **Frontend (futuro):** calcular `max_progress_chunk_id` (+ opcional
  `current_block_id`) desde el scroll, en vez de `section`.

**Regla de cierre:** cuando acordemos los nombres finales, escríbelos en un
handoff nuevo en `agent_log/` (o edita este). Yo implemento mi lado contra eso.
No edites `contracts.py`/`resolver.py` (son míos); proponme los nombres y yo los
aplico, así no chocan dos agentes en el mismo archivo.

---

## Prompt para pasarle al agente de Chang

> Copia/pega esto a tu agente de terminal, junto con acceso al repo.

```
Lee, en este orden:
  1. AGENTS.md
  2. agent_log/2026-07-07-reconciliacion-scope-antispoiler.md   (este doc)
  3. agent_log/2026-07-05-preprocessing-pipeline.md
  4. src/companion/corpus/book_master.py y canonical_text.py

Contexto: Giano (dueño de agent/tools/contracts.py y scope/resolver.py) y Chang
(dueño de chunking/preprocessing/QA-RAG) diseñaron "progreso de lectura" con dos
unidades distintas. Giano usó `section`; Chang usa `chunk_id` (y `block_id`).
Giano RECOMIENDA adoptar el eje `chunk_id` de Chang (razones en el doc §"Mi
modelo mental"). El anti-spoiler se mide por chunk_id; las secciones quedan para
navegación/pausas, no para censura.

Tu tarea, JUNTO CON Chang (humano), es CERRAR las 5 sub-decisiones del doc
(§"Sub-decisiones"): doble id int/string, revelado parcial por bloque sí/no ya,
quién construye el catálogo runtime (propuesta: index_book es de Chang),
secciones como eje de scope, y si se mantiene last_completed_section. Para cada
una, pregúntale a Chang lo que no puedas decidir desde el código; no inventes.

Cuando esté cerrado:
  - Implementa el lado de Chang: jobs/index_book.py debe (a) derivar del master
    el catálogo runtime [{chunk_id:int, section_ids, char_start, char_end,
    chroma_id}] y (b) indexar retrieval.jsonl en ChromaDB con chroma_id +
    char_start/char_end en metadata. Confirma la semántica del anti-spoiler por
    chunk/bloque en runtime.
  - NO edites agent/tools/contracts.py ni scope/resolver.py (son de Giano).
    En su lugar, escribe los nombres/forma finales acordados en un handoff nuevo
    en agent_log/ para que Giano implemente su lado contra eso.
  - Respeta los 4 contratos que no se rompen (AGENTS.md). El texto canónico es
    build_canonical_text() = "\n\n".join(chunk.text); no lo re-normalices.

Entregable: el catálogo + indexación implementados, y un handoff en agent_log/
con el contrato final de ReadingState/ScopeChunk acordado con Chang.
```
