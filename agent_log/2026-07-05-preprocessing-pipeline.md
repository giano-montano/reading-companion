# Handoff — pipeline de preprocessing de libros

**Fecha:** 2026-07-05
**Autor:** agente de Chang
**Estado:** vivo — actualizable en cada commit que toque `data/estructura.md` o `data/master/master.md`

## Qué construimos

Un pipeline que toma un EPUB (`data/source/<epub>`) y produce los 3 outputs
del flujo acordado en `data/estructura.md` con **estructura plana por tipo de
artefacto, sin subcarpetas por libro**:

```
data/source/<epub>                              (entrada; no se modifica)
data/master/<book_id>.master.json               (fuente de verdad editable)
data/outputs/readers/<book_id>.reader.json      (frontend; derivado puro)
data/outputs/retrievals/<book_id>.retrieval.jsonl  (RAG; derivado puro)

data/master/<book_id>.checkpoints.json          (opcional; pausas pedagógicas a mano)
```

`reader.json` y `retrieval.jsonl` son **100 % derivables** del master; nunca
se editan a mano.

Libro piloto de esta iteración: `la_metamorfosis_es` (Kafka, 3 capítulos).

## Decisiones de contrato (cambios sobre `data/master/master.md`)

1. **`Chunk.section_ids: list[int]`** (no `int`). Un chunk puede cubrir varias
   secciones — eso ya está en `master.md` actualizado. Reflejado en `BookChunk`.

2. **`book_id`** = snake_case del título en español. Para La Metamorfosis:
   `la_metamorfosis_es`. Estable; no cambia tras publicar. Coincide con el
   nombre del archivo master (`<book_id>.master.json`) y con el nombre de la
   carpeta de reader/retrieval.

3. **Secuencia de IDs** = enteros autoincrementales por libro, partiendo en 1.
   `section_id`, `block_id`, `chunk_id` se asignan en orden de lectura.

4. **`chunk_id` del master es `int`** (1, 2, 3…). El `chunk_id` que va a Chroma
   es `f"{book_id}::chunk_{i}::text"` (string) o `::question_{j}` — el mapping
   lo hace el indexador, no el master. Esto evita tocar `Chunk` de `schemas.py`.

5. **`BookMaster`** = nuevo modelo pydantic en `companion/corpus/book_master.py`
   que refleja EXACTAMENTE `data/master/master.md`. Los schemas en
   `companion/schemas.py` no se tocan (Chang es dueño).

6. **Estructura de directorios plana** (decisión 2026-07-05). Ya no existe
   `data/books/<book_id>/`. Los archivos se organizan por tipo:
   `data/master/`, `data/outputs/readers/`, `data/outputs/retrievals/`.

7. **Secciones (pausas pedagógicas) son manuales** (decisión 2026-07-05).
   El default (`--checkpoints=none`) produce un master con `sections: []` y
   todos los `block.section_id = null`. Para marcar pausas, el usuario
   crea un `data/master/<book_id>.checkpoints.json` y re-corre el pipeline
   con `--checkpoints=json --checkpoints-json=...`. El `HeuristicCheckpointResolver`
   existe solo para exploración y emite un warning al activarse.

8. **Año de publicación es manual** (decisión 2026-07-05). Prioridad:
   `--year` (CLI) > DC date del EPUB (si válida, rango 1000-año_actual+1) >
   ERROR. El script **nunca** improvisa un año.

## Decisiones de implementación

1. **Encoding del EPUB**: el de La Metamorfosis declara `utf-8` pero está en
   latin-1. Estrategia: intentar utf-8; si produce U+FFFD, fallback a latin-1.
   Suficiente para MVP; si hay libros en más encodings se sustituye por
   `chardet`.

2. **Parser HTML**: `BeautifulSoup(text, 'html.parser')` sobre el texto
   ya decodificado. `lxml` rompía la codificación del EPUB mal declarado.

3. **Limpieza de texto**: en cada bloque, reemplazar `\xad` (soft hyphen) y
   colapsar whitespace al final. No tocamos mayúsculas ni acentos.


5. **Estrategia de chunking** (parametrizable en `companion/chunkers/narrative.py`):
   - Target 220–320 tokens; mín 80–120; máx 400; flexible 500.
   - Cierra en límites de párrafo / diálogo.
   - **No cierra en checkpoints** (per `master.md` v2).
   - Si un bloque aislado > max_flexible, se parte por oración antes de añadir.
   - Sin overlap persistente.
   - Constructor con todos los parámetros: `NarrativeChunker(target_tokens=270,
     min_tokens=100, max_tokens=400, max_flexible_tokens=500)`.

6. **Contador de tokens**: proxy = `len(text.split()) * 1.3`. Suficiente para
   español; no añadimos `tiktoken`.

7. **Texto canónico** (en `companion/corpus/canonical_text.py`):
   `"\n\n".join(chunk.text for chunk in chunks)`. El `char_start`/`char_end`
   se calculan sobre este string. Es la única normalización — si cambia, se
   invalidan todos los offsets persistidos en Chroma (contrato #1).

8. **Preguntas hipotéticas** (en `companion/corpus/retrieval_writer.py`):
   - 5 por chunk. Prompt en español; espera JSON array de 5 strings.
   - Usa `MockLLMProvider` por default (sin API key). El `MockLLMProvider`
     ya tiene un canned para "array json".
   - Si `LLM_PROVIDER` real (nvidia), usa `get_content_llm()` y cachea.

## Lo que NO cambia

- `companion/schemas.py` (F1). `Chunk`/`EnrichedChunk` siguen siendo los del
  runtime F1.
- `companion/agent/tools/contracts.py` (Giano es dueño).
- `companion/scope/resolver.py` (Giano es dueño). El catálogo de chunks
  (`ChunkRef`) lo consumimos nosotros del master.
- `companion/providers/factory.py` (sigue roto — fuera de scope, no lo toco).

## Puntos de verificación para Chang (humano)

1. **Master sin secciones (default)**: `data/master/<book_id>.master.json` →
   confirmar `sections: []` y todos `block.section_id = null`. Decidir dónde
   van las pausas pedagógicas.
2. **Chunks y offsets**: revisar `chunks[]` y `blocks[].chunk_id` → ¿los
   tamaños son razonables? ¿los offsets satisfacen
   `canonical[char_start:char_end] == text`?
3. **Reader**: `data/outputs/readers/<book_id>/reader.json` → si no hay
   secciones, `sections: []` y no hay checkpoints. Si las marcaste con
   `checkpoints.json`, validar que `start_block_id`/`end_block_id` están
   bien asignados.
4. **Retrieval**: `data/outputs/retrievals/<book_id>/retrieval.jsonl` → validar
   que las preguntas hipotéticas son variadas y útiles; las 5 por chunk.

## Runbook

```bash
# sin pausas, año del EPUB (o error si no tiene):
.venv\Scripts\python.exe -m companion.cli.preprocess \
    La_Metamorfosis-Kafka_Franz.epub \
    --book-id la_metamorfosis_es

# con pausas manuales y año fijo:
.venv\Scripts\python.exe -m companion.cli.preprocess \
    La_Metamorfosis-Kafka_Franz.epub \
    --book-id la_metamorfosis_es \
    --year 1915 \
    --checkpoints=json \
    --checkpoints-json=data/master/la_metamorfosis_es.checkpoints.json

# exploración (warning de "no son pausas pedagógicas"):
.venv\Scripts\python.exe -m companion.cli.preprocess \
    La_Metamorfosis-Kafka_Franz.epub \
    --book-id la_metamorfosis_es --checkpoints=heuristic
```
