# Handoff — pipeline de preprocessing de libros

**Fecha:** 2026-07-06
**Autor:** agente de Chang
**Estado:** vivo

## Alcance real (julio 2026)

Generar los 3 archivos derivados de un EPUB:

```
data/source/<epub>
        ↓
data/master/<book_id>.master.json               (fuente de verdad)
data/outputs/readers/<book_id>.reader.json      (frontend; derivado puro)
data/outputs/retrievals/<book_id>.retrieval.jsonl  (RAG; derivado puro)
```

**Fuera de scope** (aplazado para sesiones futuras):
- Indexación vectorial (ChromaDB). No hay `chroma_db/`.
- Cambio de modelo de embeddings (se mantiene MiniLM default de F1).
- `BlockSplitter` — no implementado en esta iteración.
- E5 prefixes (`passage:` / `query:`) — no implementados.
- `reindex` CLI — no existe.

## Pipeline (simplificado)

```
EpubBookLoader        → 198 RawBlocks (HTML limpio, sin class/id/span)
        ↓
_to_book_blocks       → BookBlocks (section_id=null, is_narrative)
        ↓
NarrativeChunker      → asigna chunk_id, crea chunks[]
        ↓
recompute_offsets     → char_start / char_end sobre texto canónico
        ↓
master / reader / retrieval writers
```

## Código activo en `companion/corpus/`

| Archivo | Rol |
|---|---|
| `epub_loader.py` | EPUB → RawBlock. HTML sin atributos, sin `<span>`. Fallback utf-8 → latin-1. |
| `book_master.py` | `BookMaster`, `BookBlock`, `BookChunk` (pydantic v2). `start_block_id`/`end_block_id` opcionales (default 0), no se publican. |
| `book_builder.py` | Orquestador simple. EPUB → chunk → writers. **Sin lógica de checkpoints.** |
| `canonical_text.py` | `build_canonical_text()`, `recompute_offsets()`, `validate_offsets()`. |
| `master_writer.py` | `book.master.json`. Bloques: `id, section_id, content, text, chunk_id, is_narrative`. Chunks: `id, section_ids, text, char_start, char_end`. |
| `reader_writer.py` | `reader.json`. Bloques: `id, section_id, content, text, chunk_id`. |
| `retrieval_writer.py` | `retrieval.jsonl`. Metadata: `book_id, section_ids`. |
| `sectioner.py` | `apply_pauses(master, spots)` — parte bloques, renumera, asigna section_ids, re-corre chunker. Se usa DESPUÉS de generar el master. |

**Eliminados:** `base.py` (CorpusLoader ABC, nunca importado), `checkpoints.py` (CheckpointResolver, reemplazado por sectioner).

## Decisiones de contrato (resumen actualizado)

### IDs
- `book_id`: snake_case estable (`la_metamorfosis_es`).
- `section_id`, `block_id`, `chunk_id`: enteros autoincrementales por libro.

### Secciones (pausas pedagógicas)
- **No existe `checkpoints.json`.** Las secciones se aplican al final con `sectioner.apply_pauses()`.
- El master se genera con `sections: []` y `block.section_id = null`.
- Para marcar pausas: se pasan `SectionSpot(block_id, split_after=None)` al sectioner.
- Si una pausa cae dentro de un bloque: el sectioner lo parte en dos, renumera, asigna section_id.
- Los chunks pueden cruzar secciones (tener ≥2 `section_ids`).
- La relación bloque→sección está en `blocks[].section_id`.

### Chunks
- `id`: autoincremental.
- `section_ids: list[int]` — sin null, en orden, sin duplicados.
- `start_block_id`/`end_block_id`: existen en el modelo (uso interno del chunker) pero **no se publican** en master ni retrieval.
- Relación bloque→chunk: `blocks[].chunk_id`.

### Anti-spoiler (por chunk_id)
```
chunks con id < current_chunk_id  → completos (chunk.text entero)
chunk  con id == current_chunk_id → parcial ("\n\n".join(blocks hasta current_block_id))
chunks con id > current_chunk_id  → no se usan
```

### Regla `\n\n` (única fuente de verdad)
```
chunk.text = "\n\n".join(b.text for b in blocks if b.chunk_id == chunk.id)
```
El chunker y el backend en runtime usan la misma regla.

### Bloques
- `id`: autoincremental.
- `content`: HTML semántico limpio (`<p>`, `<h1>`–`<h3>`, `<blockquote>`, `<hr>`, `<nav>`) **sin atributos** (class, id, style) y **sin `<span>`**.
- `text`: texto plano, sin HTML.
- `is_narrative`: true para `<p>` y `<blockquote>` con texto.
- `chunk_id`: el chunk al que pertenece.

### Preguntas hipotéticas
- La Metamorfosis (versión final): generadas manualmente por el agente — 4-5 por chunk, específicas al contenido, sin dependencia del LLM.
- `retrieval_writer.py` existe como boilerplate para otros libros, pero usa `MockLLMProvider` (factory roto).

## Runbook

```bash
# Generar master + reader + retrieval desde un EPUB:
.venv\Scripts\python.exe -m companion.cli.preprocess \
    La_Metamorfosis-Kafka_Franz.epub \
    --book_id la_metamorfosis_es \
    --year 1915

# Aplicar pausas pedagógicas (después de generar el master):
python -c "
from companion.corpus.book_master import BookMaster
from companion.corpus.sectioner import apply_pauses, SectionSpot
import json
master = BookMaster.model_validate(json.load(open('data/master/la_metamorfosis_es.master.json')))
spots = [SectionSpot(block_id=4, split_after='monstruoso insecto'), ...]
master = apply_pauses(master, spots)
# ... write master, reader, retrieval
"
```

## Lo que NO se toca (áreas de otros dueños)

- `companion/schemas.py` (F1 runtime).
- `companion/agent/tools/contracts.py` (Giano).
- `companion/scope/resolver.py` (Giano).
- `companion/providers/factory.py` (sigue roto — fuera de scope).
- `companion/vector_store/`, `retrieval/`, `enrichers/`, `agent/`, `api/` — documentados en README pero no usados en este pipeline.

## Archivos generados (no commiteados)

- `data/master/la_metamorfosis_es.master.json` (fuente de verdad, se regenera)
- `data/outputs/readers/la_metamorfosis_es.reader.json`
- `data/outputs/retrievals/la_metamorfosis_es.retrieval.jsonl`

## Decisiones abiertas

- ¿Reescribir `NarrativeChunker` con cierre por distancia al target?
- ¿Migrar embeddings a E5?
- ¿Implementar `BlockSplitter` (split de bloques oversized antes del chunker)?
- ¿Indexar en ChromaDB?
- ¿Arreglar `providers/factory.py` (está roto con syntax errors)?
