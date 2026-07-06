
# Estructura de `reader.json`

`reader.json` es el archivo que consume el frontend para mostrar el libro.

Se genera desde `book.master.json`.

No contiene el texto consolidado de los chunks ni offsets por caracteres. Conserva `chunk_id` dentro de los bloques narrativos y los límites de cada sección para conocer el contexto de lectura y materializar checkpoints.

## Estructura

```json
{
  "book_id": "el_principito_es",

  "metadata": {
    "title": "El Principito",
    "author": "Antoine de Saint-Exupéry",
    "publication_year": 1943
  },

  "sections": [
    {
      "id": 1,
      "start_block_id": 3,
      "end_block_id": 5
    },
    {
      "id": 2,
      "start_block_id": 6,
      "end_block_id": 8
    }
  ],

  "blocks": [
    {
      "id": 1,
      "section_id": null,
      "content": "<h1>El Principito</h1>",
      "chunk_id": null
    },
    {
      "id": 2,
      "section_id": 1,
      "content": "<h2>Capítulo I</h2>",
      "chunk_id": null
    },
    {
      "id": 3,
      "section_id": 1,
      "content": "<p>Cuando yo tenía seis años vi una vez una lámina magnífica...</p>",
      "chunk_id": 1
    },
    {
      "id": 4,
      "section_id": 1,
      "content": "<p>Mi dibujo no representaba un sombrero...</p>",
      "chunk_id": 1
    }
  ]
}
```

## Campos

| Campo                     | Uso                                                       |
| ------------------------- | --------------------------------------------------------- |
| `book_id`                 | Identifica la obra abierta.                               |
| `metadata`                | Muestra título, autor y año.                              |
| `sections`                | Define unidades de lectura y la ubicación de checkpoints. |
| `sections[].end_block_id` | Indica después de qué bloque aparece la pausa pedagógica. |
| `blocks`                  | Elementos visibles en orden de lectura.                   |
| `blocks[].id`             | Identifica el bloque visible.                             |
| `blocks[].section_id`     | Identifica la sección actual.                             |
| `blocks[].content`        | HTML sanitizado que se renderiza.                         |
| `blocks[].chunk_id`       | Contexto RAG del bloque narrativo.                        |

## Renderizado

El frontend carga el `reader.json` completo una vez al abrir el libro.

Para el MVP, está bien renderizar el libro completo dentro de un contenedor scrolleable.

```tsx
<article className="reader-container">
  {reader.blocks.map((block) => {
    const completedSection = reader.sections.find(
      (section) => section.end_block_id === block.id
    );

    return (
      <Fragment key={block.id}>
        <div
          id={`block-${block.id}`}
          data-block-id={block.id}
          data-section-id={block.section_id ?? undefined}
          data-chunk-id={block.chunk_id ?? undefined}
          dangerouslySetInnerHTML={{ __html: block.content }}
        />

        {completedSection && (
          <ReadingCheckpoint sectionId={completedSection.id} />
        )}
      </Fragment>
    );
  })}
</article>
```

El checkpoint es un componente del frontend. No forma parte del HTML narrativo del libro ni del RAG.

No se debe guardar un documento HTML completo:

```html
<html>
  <body>...</body>
</html>
```

Solo fragmentos pequeños:

```html
<p>Texto narrativo...</p>
<h2>Capítulo I</h2>
<p><em>Texto en cursiva</em>.</p>
```

## Contexto de lectura

Cuando el alumno pregunta, el frontend detecta el bloque visible actual y envía:

```json
{
  "book_id": "el_principito_es",
  "current_section_id": 1,
  "current_block_id": 4,
  "current_chunk_id": 1,
  "question": "¿Por qué el narrador dejó de dibujar?"
}
```

`current_block_id` es obligatorio para evitar spoilers dentro del mismo chunk.

Los bloques con:

```json
{
  "chunk_id": null
}
```

se muestran normalmente, pero no representan texto narrativo para el RAG.

Ejemplos:

```text
Portada
Índice
Títulos
Separadores
Créditos
```

`reader.json` no necesita `char_start` ni `char_end`.

---
