# Handoff — pipeline de preprocessing de libros

**Fecha:** 2026-07-05
**Autor:** agente de Chang
**Estado:** vivo — actualizable en cada commit que toque `data/estructura.md` o `data/master/master.md`

## Qué construimos

Un pipeline que toma un EPUB (`data/source/<epub>`) y produce los 3 outputs
del flujo acordado en `data/estructura.md`:

```
data/books/<book_id>/
  source/original.epub
  preprocessing/
    book.master.json
    checkpoints.json            (opcional; override manual de checkpoints)
  prepared/
    reader/reader.json
    retrieval/retrieval.jsonl
```

Libro piloto de esta iteración: `la_metamorfosis_es` (Kafka, 3 capítulos).

## Decisiones de contrato (cambios sobre `data/master/master.md`)

1. **`Chunk.section_ids: list[int]`** (no `int`). Un chunk puede cubrir varias
   secciones — eso ya está en `master.md` actualizado. Reflejado en `BookChunk`.

2. **`book_id`** = snake_case del título en español. Para La Metamorfosis:
   `la_metamorfosis_es`. Estable; no cambia tras publicar.

3. **Secuencia de IDs** = enteros autoincrementales por libro, partiendo en 1.
   `section_id`, `block_id`, `chunk_id` se asignan en orden de lectura.

4. **`chunk_id` del master es `int`** (1, 2, 3…). El `chunk_id` que va a Chroma
   es `f"{book_id}::chunk_{i}::text"` (string) o `::question_{j}` — el mapping
   lo hace el indexador, no el master. Esto evita tocar `Chunk` de `schemas.py`.

5. **No tocamos** la ABC `CorpusLoader` (queda para el F1 de textos `.txt`).
   El preprocessing de libros es una familia nueva: `EpubBookLoader` y
   `BookBuilder` en `companion/corpus/`, que producen `BookMaster` (modelo
   nuevo) en vez de `Iterator[Document]`.

6. **`BookMaster`** = nuevo modelo pydantic en `companion/corpus/book_master.py`
   que refleja EXACTAMENTE `data/master/master.md`. Los schemas en
   `companion/schemas.py` no se tocan (Chang es dueño).

## Decisiones de implementación

1. **Encoding del EPUB**: el de La Metamorfosis declara `utf-8` pero está en
   latin-1. Estrategia: intentar utf-8; si produce U+FFFD, fallback a latin-1.
   Suficiente para MVP; si hay libros en más encodings se sustituye por
   `chardet`.

2. **Parser HTML**: `BeautifulSoup(text, 'html.parser')` sobre el texto
   ya decodificado. `lxml` rompía la codificación del EPUB mal declarado.

3. **Limpieza de texto**: en cada bloque, reemplazar `\xad` (soft hyphen) y
   colapsar whitespace al final. No tocamos mayúsculas ni acentos.

4. **Estrategia de checkpoints (parametrizable)** en `companion/corpus/checkpoints.py`:
   - `HeuristicCheckpointResolver` (default): cada `<h1>` o `<h2>` no vacío
     marca un nuevo checkpoint. Los bloques con `section_id: null` (portada,
     título, créditos) se asignan como `null`.
   - `JsonCheckpointResolver`: lee `data/books/<id>/preprocessing/checkpoints.json`
     con la forma `{ "sections": [ {"start_block_id": N}, ... ] }` y aplica el
     override.
   - Intercambiables vía el flag `--checkpoints=heuristic|json`.

5. **División de bloques** (parametrizable en `companion/corpus/block_splitting.py`):
   - `--split-blocks/--no-split-blocks`. Default: ON.
   - Si un checkpoint cae dentro de un bloque `<p>`, lo parte por oración
     (heurística simple: split en `. `, `? `, `! `).
   - Si el bloque no se puede partir limpiamente, se deja entero y se avisa
     (no es error).

6. **Estrategia de chunking** (parametrizable en `companion/chunkers/narrative.py`):
   - Target 220–320 tokens; mín 80–120; máx 400; flexible 500. (definido en
     `data/master/master.md` §"Estrategia de chunking")
   - Cierra en límites de párrafo / diálogo.
   - **No cierra en checkpoints** (per `master.md` v2).
   - Si un bloque aislado > max_flexible, se parte por oración antes de añadir.
   - Sin overlap persistente.
   - Constructor con todos los parámetros: `NarrativeChunker(target_tokens=270,
     min_tokens=100, max_tokens=400, max_flexible_tokens=500)`.

7. **Contador de tokens**: proxy = `len(text.split()) * 1.3`. Suficiente para
   español; no añadimos `tiktoken`.

8. **Texto canónico** (en `companion/corpus/canonical_text.py`):
   `"\n\n".join(chunk.text for chunk in chunks)`. El `char_start`/`char_end`
   se calculan sobre este string. Es la única normalización — si cambia, se
   invalidan todos los offsets persistidos en Chroma (contrato #1).

9. **Preguntas hipotéticas** (en `companion/corpus/retrieval_writer.py`):
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

1. **Después de Fase 1 (master borrador)**: revisar `book.master.json` →
   ¿la lista de bloques y las secciones reflejan lo que tú querés? ¿Falta
   algún título, sobra algún bloque?
2. **Después de Fase 2 (chunks)**: revisar `chunks[]` y `blocks[].chunk_id` →
   ¿los tamaños son razonables? ¿los chunks respetan la lectura (no parten
   a la mitad de un diálogo)?
3. **Después de Fase 3 (reader.json)**: abrir el json y validar visualmente
   que `sections[].start_block_id` y `end_block_id` están bien asignados.
4. **Después de Fase 4 (retrieval.jsonl)**: validar que las preguntas
   hipotéticas son variadas y útiles; las 5 por chunk.
