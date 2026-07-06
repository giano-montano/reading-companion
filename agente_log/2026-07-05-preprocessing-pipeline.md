# Handoff — pipeline de preprocessing de libros

**Fecha:** 2026-07-05
**Autor:** agente de Chang (área: chunking, QA-RAG, retrieval)
**Estado:** vivo — actualizable en cada commit que toque `data/estructura.md` o `data/master/master.md`

## Alcance de esta sesión

Generar los 3 archivos derivados de un EPUB:

```
data/source/<epub>
        ↓
data/master/<book_id>.master.json               (fuente de verdad)
data/outputs/readers/<book_id>.reader.json      (frontend; derivado puro)
data/outputs/retrievals/<book_id>.retrieval.jsonl  (RAG; derivado puro)
```

**No se hace en esta sesión** (dejado para iteraciones futuras):
- Indexación vectorial (ChromaDB). El usuario borró `chroma_db/` y
  quiere aplazar la base vectorial.
- Cambio de modelo de embeddings a E5. Mantenemos
  `paraphrase-multilingual-MiniLM-L12-v2` (config default, sin cambios).
- Reescritura del `NarrativeChunker`. Mantenemos la versión simple de
  F1 con cierre por umbrales (`target`/`max`).
- Token counter del embedder. El `get_token_counter()` queda como
  helper opcional, no se usa por defecto en el chunker simple.

## Decisiones de contrato (vivas)

1. **`Chunk.section_ids: list[int]`** (no `int`). Un chunk puede cubrir
   varias secciones — reflejado en `BookChunk` (`companion/corpus/
   book_master.py`).

2. **`book_id`** = snake_case del título en español. Estable; coincide con
   el nombre del archivo master y de los outputs.

3. **Secuencia de IDs** = enteros autoincrementales por libro.

4. **`chunk_id` del master es `int`**. El `chunk_id` que va a Chroma
   (`<book_id>::chunk_<n>::text`) lo construye el indexador, no el master.

5. **No tocamos** la ABC `CorpusLoader` (F1). El preprocessing de
   libros es una familia nueva: `EpubBookLoader` y `BookBuilder` en
   `companion/corpus/`, que producen `BookMaster` (modelo nuevo) en
   vez de `Iterator[Document]`.

6. **Estructura de directorios plana** (ver `data/estructura.md`):
   ```
   data/master/<book_id>.master.json
   data/outputs/readers/<book_id>.reader.json
   data/outputs/retrievals/<book_id>.retrieval.jsonl
   ```
   Sin subcarpetas por libro.

7. **Secciones (pausas pedagógicas) son manuales**. Default
   (`--checkpoints=none`): master con `sections: []` y todos los
   `block.section_id = null`. Para marcar pausas, el usuario crea un
   `data/master/<book_id>.checkpoints.json` y re-corre con
   `--checkpoints=json --checkpoints-json=...`.

8. **Año de publicación es manual**. Prioridad: `--year` (CLI) > DC
   date del EPUB (si válida, rango 1000-año_actual+1) > ERROR. El
   script **nunca** improvisa un año.

9. **Encoding del EPUB**: el de La Metamorfosis declara `utf-8` pero
   está en latin-1. Estrategia: intentar utf-8; si produce U+FFFD,
   fallback a latin-1. Suficiente para MVP.

10. **Parser HTML**: `BeautifulSoup(text, 'html.parser')` sobre el
    texto ya decodificado. `lxml` rompía la codificación del EPUB
    mal declarado.

11. **Estrategia de checkpoints** en `companion/corpus/checkpoints.py`:
    - `--checkpoints=none` (default): no se marcan secciones.
    - `--checkpoints=json`: lee un archivo JSON con la forma
      `{"sections": [{"start_block_id": N, "note": "..."}, ...]}`.
    - `--checkpoints=heuristic`: cada `<h1>` o `<h2>` no vacío abre
      sección. Emite warning de "esto NO son pausas pedagógicas".

## Pipeline

```
EpubBookLoader
   ↓
[raw blocks con IDs únicos]
   ↓
(CheckpointResolver, opcional)
   ↓
NarrativeChunker                    ← versión simple (F1, target/max)
   ↓
recompute canonical offsets
   ↓
master / reader / retrieval writers
```

## Lo que NO está en este handoff

- `vector_store/`, `retrieval/`, `embedders/factory.py`,
  `enrichers/`, `providers/factory.py`, `agent/`, `api/`, `scope/`:
  existen como paquetes documentados en `README.md` y `AGENTS.md`
  (áreas de otros dueños o trabajo futuro). El pipeline actual no
  los usa para generar master/reader/retrieval.
- `jobs/indexing.py` (F1): eliminado en la limpieza 2026-07-05.
- `corpus/text_loader.py` y `corpus/block_splitting.py` (F1):
  eliminados en la limpieza 2026-07-05.

## Runbook

```bash
# preprocess (EPUB -> master + reader + retrieval):
.venv\Scripts\python.exe -m companion.cli.preprocess \
    La_Metamorfosis-Kafka_Franz.epub \
    --book-id la_metamorfosis_es \
    --year 1915

# con pausas pedagógicas manuales:
.venv\Scripts\python.exe -m companion.cli.preprocess \
    La_Metamorfosis-Kafka_Franz.epub \
    --book-id la_metamorfosis_es \
    --year 1915 \
    --checkpoints=json \
    --checkpoints-json=data/master/la_metamorfosis_es.checkpoints.json
```

## Decisiones abiertas / próximas sesiones

- ¿`NarrativeChunker` se reescribe con cierre por distancia al target
  + `BlockSplitter` upstream? (Aplazado.)
- ¿Migrar embeddings a E5 (`intfloat/multilingual-e5-base`)? (Aplazado.)
- ¿Indexar en ChromaDB? (Aplazado — el usuario borró `chroma_db/`.)
