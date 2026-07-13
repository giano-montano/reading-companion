# Archivo: `data/estructura.md`

# Estructura general de libros

Los libros se guardan en una estructura **plana por tipo de artefacto**, no
por libro. Cada libro se identifica por su `book_id` (string global estable).

```text
data/
  source/                                  EPUBs originales (sin modificar)
    La_Metamorfosis-Kafka_Franz.epub
    Las_aventuras_de_Tom_Sawyer-Mark_Twain.epub
    ...

  master/                                  Masters: uno por libro, aplanado
    la_metamorfosis_es.master.json
    las_aventuras_de_tom_sawyer_es.master.json
    ...
    master.md                              (este archivo: documentación del schema)

  outputs/
    readers/                               Readers: un archivo por libro
      la_metamorfosis_es.reader.json
      las_aventuras_de_tom_sawyer_es.reader.json
      ...
      reader.md                            (documentación del schema)

    retrievals/                            Retrievals: un archivo por libro
      la_metamorfosis_es.retrieval.jsonl
      las_aventuras_de_tom_sawyer_es.retrieval.jsonl
      ...
      retrievals.md                        (documentación del schema)
```

No hay subcarpetas por libro: los outputs son **derivados puros** del
master y se regeneran cada vez. El master es la única fuente editable.

## Flujo general

```text
data/source/<epub>                                (entrada, no se modifica)
        ↓
data/master/<book_id>.master.json                 (fuente de verdad editable)
        ↓
data/outputs/readers/<book_id>.reader.json        → frontend
data/outputs/retrievals/<book_id>.retrieval.jsonl → embeddings y base vectorial
```

`book.master.json` es la fuente de verdad. El frontend consume
`<book_id>.reader.json` y el pipeline RAG consume
`<book_id>.retrieval.jsonl`. Ambos son **100 % derivables del master**;
nunca se editan a mano como fuente principal. Los cambios estructurales se
hacen en el master y luego se regeneran.

## `source/`

```text
source/
  La_Metamorfosis-Kafka_Franz.epub
  ...
```

Contiene los EPUB originales. **No se modifican** ni se usan directamente
desde el frontend o el RAG. Sirven para volver a procesar un libro si hay
que corregir texto, secciones, bloques o chunks.

El script de preprocessing los busca aquí por defecto
(`data/source/<filename>`) o acepta rutas absolutas.

## `master/`

```text
master/
  la_metamorfosis_es.master.json
  master.md
```

Contiene la estructura editorial y técnica central de cada libro. Un archivo
por libro, nombrado `<book_id>.master.json`.

`book.master.json` incluye:

* metadatos básicos (título, autor, año, idioma);
* secciones (pausas pedagógicas manuales — puede estar vacío);
* bloques HTML para renderizar;
* chunks narrativos limpios;
* relación entre bloques, secciones y chunks.

`master.md` documenta el schema.

### Archivo opcional de pausas pedagógicas

Para marcar las pausas pedagógicas a mano, el usuario crea (separado del
master) un archivo de checkpoints con la forma:

```json
{ "sections": [
    { "start_block_id": 23, "note": "Pausa tras la transformación" },
    { "start_block_id": 78, "note": "Pausa tras la visita del gerente" }
]}
```

Por convención se guarda junto al master:

```text
master/
  la_metamorfosis_es.master.json
  la_metamorfosis_es.checkpoints.json   ← opcional, solo si hay pausas
```

El script `companion preprocess` lo lee cuando se invoca con
`--checkpoints=json --checkpoints-json=<ruta>`. Si no existe, el master
sale con `sections: []` y todos los `blocks[].section_id = null`.

## `outputs/readers/<book_id>/`

```text
outputs/readers/la_metamorfosis_es/
  reader.json
```

Archivo que consume el frontend para mostrar el libro. Se genera desde
`book.master.json`. No contiene el texto consolidado de los chunks ni
offsets por caracteres. Conserva `chunk_id` dentro de los bloques
narrativos y los límites de cada sección para conocer el contexto de
lectura y materializar checkpoints. `reader.md` documenta el schema.

## `outputs/retrievals/<book_id>/`

```text
outputs/retrievals/la_metamorfosis_es/
  retrieval.jsonl
```

Contiene los chunks narrativos listos para indexarse en el RAG. Cada
línea es un objeto JSON independiente. `retrievals.md` documenta el
schema.

## Estrategia de IDs

```text
book_id                         → string único global
section_id, block_id, chunk_id → enteros autoincrementales por libro
```

Ejemplo:

```json
{
  "book_id": "el_principito_es",
  "section_id": 3,
  "block_id": 42,
  "chunk_id": 12
}
```

### `book_id`

Se define manualmente antes de procesar el libro. Es el prefijo de los
tres archivos por libro: `<book_id>.master.json`, `<book_id>.reader.json`
y `<book_id>.retrieval.jsonl`. Debe ser estable y no cambiar después de
publicar el libro.

```text
el_principito_es
frankenstein_es
la_metamorfosis_es
la_casa_de_carton_es
```

### `block_id`

Se genera después de extraer el EPUB, limpiar el contenido y dividir
bloques cuando un checkpoint cae dentro de un párrafo o diálogo.

Incluye portada, índice, títulos, párrafos, diálogos, separadores y
créditos.

```text
1, 2, 3, 4...
```

Representa el orden visual definitivo del libro.

### `section_id`

Se genera **manualmente** desde un `checkpoints.json` con las pausas
pedagógicas. **No** se infiere de la estructura del EPUB.

Cada sección representa una pausa pedagógica. Al terminar una sección,
se activa la actividad pedagógica correspondiente. Si no hay pausas
marcadas, `sections: []` y todos los `block.section_id = null`.

```text
1, 2, 3, 4...
```

### `chunk_id`

Se genera después de definir bloques y secciones (o, si no hay
secciones, directamente sobre los bloques narrativos).

Los chunks siguen el orden de lectura y agrupan bloques narrativos
completos. **Pueden cruzar pausas pedagógicas** — los chunks son
unidades de retrieval, las secciones son pausas pedagógicas.

```text
1, 2, 3, 4...
```

## Orden de procesamiento

```text
1. Registrar el libro
   → crear book_id (estable, snake_case)

2. Extraer y limpiar el EPUB
   → obtener bloques iniciales (loader)

3. (Opcional) Definir checkpoints pedagógicos a mano
   → crear data/master/<book_id>.checkpoints.json
   → re-correr con --checkpoints=json

4. (Opcional) Dividir bloques si un checkpoint cae dentro
   → el script lo hace automáticamente si está activado

5. Crear chunks narrativos
   → asignar chunk_id a bloques narrativos
   → calcular char_start y char_end

6. Guardar book.master.json

7. Generar reader.json

8. Generar preguntas hipotéticas y retrieval.jsonl

9. Vectorizar texto y preguntas hipotéticas
```

## Regla principal

```text
El EPUB se conserva.
El master se edita.
El reader y retrieval se generan.
```
