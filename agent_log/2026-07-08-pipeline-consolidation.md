# Handoff — consolidación del pipeline y preparación para embeddings

**Fecha:** 2026-07-08
**Autor:** agente de Giano
**Estado:** vivo

## Qué cambió

Se reemplazó el pipeline viejo (`companion/corpus/`, `companion/chunkers/`,
`companion/cli/preprocess.py`) por uno nuevo en `src/preprocesamiento/`. Los
archivos `.master.json` ahora incluyen `is_narrative` clasificado, checkpoints
`BANDERA` y `chunks` generados con tokenizer real. Los derivados reader y
retrieval se generan por separado desde el master.

### Archivos borrados

```
src/companion/corpus/      # pipeline viejo EPUB→master
src/companion/chunkers/    # chunker viejo
src/companion/cli/         # CLI vieja
```

Ningún runtime component (`api/`, `agent/`, `retrieval/`, etc.) los importaba.

## Nuevo pipeline (`src/preprocesamiento/`)

```
data/source/<epub>
        │
        ▼
build_master.py            EPUB → master.json (estructura plana, is_narrative=true)
        │
        ▼
classify_narrative.py      Corrige is_narrative (editorial → false, literario → true)
        │
        ▼
insert_banderas.py         Inserta bloques BANDERA como checkpoints de lectura
        │
        ▼
generate_chunks.py         Tokeniza con AutoTokenizer (multilingual-e5-small),
                           genera chunks con overlap, asigna chunk_id a bloques.
        │
        ├──▶ data/outputs/reader/<book_id>.reader.json       (bloques para frontend)
        │    data/outputs/reader/reader_index.json
        │
        └──▶ data/outputs/retrieval/<book_id>.retrieval.jsonl  (chunks para RAG)
             data/outputs/retrieval/retrieval_all.jsonl
             data/outputs/retrieval/retrieval_summary.json
```

### Estructura del master.json

```json
{
  "book_id": "...",
  "metadata": { "title", "author", "publication_year" },
  "blocks": [
    {
      "id_block": "...::block::n",
      "type": "p" | "h1" | "h2" | "h3" | "BANDERA",
      "text": "...",
      "chunk_id": "...::chunk::n" | null,
      "char_start": int,
      "char_end": int,
      "is_narrative": bool
    }
  ],
  "chunks": [
    {
      "id_chunk": "...::chunk::n",
      "text": "...",
      "char_start": int,
      "char_end": int
    }
  ]
}
```

- Bloques `BANDERA`: `is_narrative=false`, `chunk_id=null`. Son checkpoints
  pedagógicos, no afectan el chunking ni el RAG.
- Bloques editoriales: `is_narrative=false`, `chunk_id=null`.
- Bloques narrativos: `is_narrative=true`, `chunk_id` apunta al primer chunk que
  los contiene.
- Chunks: generados con tokenizer real, overlap ~100 tokens, tamaño 350-500
  tokens. 2353 chunks totales en 8 libros.

### Parámetros de chunking

```
MIN_SEARCH_TOKENS  = 350
SOFT_MAX_TOKENS    = 470
HARD_MAX_TOKENS    = 500
OVERLAP_TARGET     = 100
OVERLAP_MIN        = 60
MIN_CHUNK_TOKENS   = 200
Tokenizer          = AutoTokenizer (intfloat/multilingual-e5-small, desde .env EMBEDDING_MODEL)
```

### Archivos de referencia

- `data/master/banderas_insertions.json` — posiciones de cada BANDERA (índices
  en el array de bloques original, para reconstruir desde master limpio).
- `data/master/index_books.json` — catálogo estático de libros (usado por la API).
- `data/master/chunking_report.txt` — reporte de tokens/chars por chunk.

## API (`src/companion/api/`)

Reorganizada en archivos por dominio:

```
api/
├── server.py          # app, middleware CORS, StaticFiles, root, /health
├── books.py           # GET /api/books
│                      # GET /api/books/{book_id}/reader
└── visual.py          # POST /api/visual-support, /preview
```

Nuevo endpoint:
- `GET /api/books/{book_id}/reader` → devuelve el reader completo (bloques +
  banderas) para el frontend.

## Estado actual (8 libros)

| book_id | bloques | narrativos | banderas | chunks |
|---|---|---|---|---|
| cronica_de_una_muerte_anunciada_gabriel_garcia_marquez | 326 | 301 | 20 | 137 |
| el_maravilloso_mago_de_oz_baum_lyman_frank | 83 | 72 | 9 | 156 |
| el_viejo_y_el_mar_ernest_hemingway | 700 | 660 | 26 | 139 |
| la_ciudad_y_los_perros_mario_vargas_llosa | 2885 | 2795 | 79 | 675 |
| la_metamorfosis_franz_kafka | 211 | 196 | 13 | 96 |
| las_aventuras_de_tom_sawyer_mark_twain | 1909 | 1839 | 52 | 382 |
| matalache_enrique_lopez_albujar | 4660 | 4497 | 128 | 354 |
| viaje_al_centro_de_la_tierra_julio_verne | 2423 | 2306 | 65 | 414 |

## Contrato del reader para frontend

El frontend consume el reader desde `GET /api/books/{book_id}/reader`. También
existe `reader_index.json` con el catálogo completo.

### `reader_index.json` (`GET /api/books`)

```json
{
  "books": [
    {
      "book_id": "la_metamorfosis_franz_kafka",
      "title": "La metamorfosis",
      "author": "Franz Kafka",
      "publication_year": 2022,
      "reader_path": "data/outputs/reader/la_metamorfosis_franz_kafka.reader.json",
      "total_blocks": 211,
      "total_narrative_blocks": 196,
      "total_non_narrative_blocks": 15,
      "total_flags": 13
    }
  ]
}
```

### `reader.json` — estructura

```json
{
  "book_id": "la_metamorfosis_franz_kafka",
  "metadata": {
    "title": "La metamorfosis",
    "author": "Franz Kafka",
    "publication_year": 2022
  },
  "blocks": [ ... ]
}
```

### Tipos de bloque que el frontend debe renderizar

Cada bloque tiene `id_block`, `type`, `text`, `is_narrative`, `char_start`,
`char_end`, `chunk_id`. Según `type`, el frontend decide cómo mostrarlo:

**`type: "h1" | "h2" | "h3"` — títulos y subtítulos**

```json
{
  "id_block": "la_metamorfosis_franz_kafka::block::3",
  "type": "h2",
  "text": "Capítulo 1",
  "chunk_id": "la_metamorfosis_franz_kafka::chunk::1",
  "char_start": 30,
  "char_end": 40,
  "is_narrative": true
}
```
- `is_narrative: true` si es título de capítulo real (parte del libro).
- `is_narrative: false` si es portada, índice, metadata editorial.
- El frontend puede optar por no renderizar bloques con `is_narrative: false`
  en el flujo de lectura, o mostrarlos atenuados como "paratexto".

**`type: "p"` — párrafos narrativos y diálogos**

```json
{
  "id_block": "la_metamorfosis_franz_kafka::block::4",
  "type": "p",
  "text": "Cuando Gregorio Samsa se despertó una mañana...",
  "chunk_id": "la_metamorfosis_franz_kafka::chunk::1",
  "char_start": 42,
  "char_end": 575,
  "is_narrative": true
}
```
- `is_narrative: true` → contenido literario, se renderiza normalmente.
- `is_narrative: false` → editorial, créditos, notas legales. El frontend
  puede ocultarlos o mostrarlos en un panel de "información del libro".

**`type: "BANDERA"` — checkpoint de lectura**

```json
{
  "id_block": "la_metamorfosis_franz_kafka::block::14",
  "type": "BANDERA",
  "text": "--$CHECKPOINT_LECTURA$--",
  "chunk_id": null,
  "char_start": -1,
  "char_end": -1,
  "is_narrative": false
}
```
- **Siempre** `is_narrative: false`, `chunk_id: null`, `char_start: -1`,
  `char_end: -1`.
- El frontend debe pausar la lectura aquí y activar una interacción pedagógica
  (pregunta, predicción, reflexión, verificación de comprensión).
- **No** es contenido para mostrar como texto. Es una señal de control.
- Se insertan cada ~15-35 bloques narrativos, solo en zonas con
  `is_narrative: true`.

### Orden de renderizado

El array `blocks` está en orden de lectura. El frontend itera secuencialmente:

```
bloque p (narrativo)     → mostrar texto
bloque p (narrativo)     → mostrar texto
bloque BANDERA           → pausa pedagógica, no mostrar texto
bloque h2 (título cap)   → mostrar como encabezado
bloque p (narrativo)     → mostrar texto
...
bloque p (no narrativo)  → ocultar o mostrar en panel aparte
```

Para anti-spoiler: el frontend envía `char_start` del último bloque leído. El
backend filtra chunks con `chunk.char_start > progreso_char_start`.

### Endpoints

| Método | Ruta | Respuesta |
|---|---|---|
| `GET` | `/api/books` | `reader_index.json` — catálogo de libros |
| `GET` | `/api/books/{book_id}/reader` | `reader.json` — bloques del libro |

`{book_id}` es el snake_case estable (ej. `la_metamorfosis_franz_kafka`).

## Próximos pasos (NO implementados)

### 1. Enriquecer los archivos retrieval con metadata

Agregar a cada línea del `.retrieval.jsonl`:
- `hypothetical_questions`: array de preguntas hipotéticas generadas por LLM
  (actualmente vacío `[]`).
- Posiblemente `embedding_text` con el prefijo E5 (`passage: ...`).
- Metadata adicional del chunk (título de capítulo/sección cercana, personajes
  detectados vía NER, etc.).

Esto se haría con un script nuevo (ej. `enrich_retrieval.py` en
`preprocesamiento/`). No modifica los master ni los reader. Solo lee retrieval y
escribe retrieval enriquecido.

### 2. Generar embeddings

A partir de `retrieval_all.jsonl` (o los `.retrieval.jsonl` enriquecidos):
- Embedding model: `intfloat/multilingual-e5-small` (o el configurado en
  `EMBEDDING_MODEL`).
- Vector store: ChromaDB (`chroma_db/`).
- Indexar cada chunk con su metadata (book_id, chunk_id, char_start, char_end,
  hypothetical_questions).
- Script: `index_embeddings.py` o similar. Usa `companion/vector_store/`.

### 3. Integrar con el agente RAG

Una vez indexado, el agente (`companion/agent/`) puede:
- Recibir queries del alumno.
- Recuperar chunks relevantes vía `companion/retrieval/`.
- Generar respuestas con el LLM de contenido (70B).
- Usar `char_start`/`char_end` para anti-spoiler (no mostrar chunks más allá
  del progreso de lectura).

## Contratos que NO cambian

1. Texto canónico: `"\n\n".join(chunk.text)` en orden de lectura.
2. Offsets absolutos: `char_start`/`char_end` sobre el texto canónico.
3. Dos LLM: router 8B + content 70B, tags de cache distintos.
4. El agente es fracción del producto: NER y estado de lectura no pasan por LLM.
