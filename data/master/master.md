# Estructura de `book.master.json`

`book.master.json` es la fuente de verdad del libro procesado.

Se guarda en `data/master/<book_id>.master.json` (un archivo por libro,
estructura plana — ver `data/estructura.md`).

Contiene la información necesaria para generar:

```text
data/outputs/readers/<book_id>/reader.json
data/outputs/retrievals/<book_id>/retrieval.jsonl
```

## Principio de diseño

Las secciones y los chunks cumplen funciones diferentes:

```text
Bloque   → unidad visible en el reader.
Sección  → unidad pedagógica que termina en un checkpoint.
Chunk    → unidad de búsqueda y vectorización para el RAG.
```

Los checkpoints no obligan a cerrar un chunk.

```text
Una sección puede estar contenida en uno o varios chunks.
Un chunk puede contener bloques de una o más secciones.
```

Esto permite que el profesor coloque checkpoints pedagógicos sin deformar artificialmente el tamaño de los chunks.

---

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
    { "id": 1 },
    { "id": 2 }
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
      "section_id": null,
      "content": "<nav><p>Índice</p></nav>",
      "chunk_id": null
    },
    {
      "id": 3,
      "section_id": 1,
      "content": "<h2>Capítulo I</h2>",
      "chunk_id": null
    },
    {
      "id": 4,
      "section_id": 1,
      "content": "<p>Cuando yo tenía seis años vi una vez una lámina magnífica...</p>",
      "chunk_id": 1
    },
    {
      "id": 5,
      "section_id": 1,
      "content": "<p>Mi dibujo no representaba un sombrero...</p>",
      "chunk_id": 1
    },
    {
      "id": 6,
      "section_id": 2,
      "content": "<h2>Capítulo II</h2>",
      "chunk_id": null
    },
    {
      "id": 7,
      "section_id": 2,
      "content": "<p>Las personas mayores me aconsejaron dejar a un lado los dibujos...</p>",
      "chunk_id": 1
    },
    {
      "id": 8,
      "section_id": 2,
      "content": "<p>Viví así solo, sin nadie con quien poder hablar verdaderamente...</p>",
      "chunk_id": 2
    }
  ],

  "chunks": [
    {
      "id": 1,
      "section_ids": [1, 2],
      "text": "Cuando yo tenía seis años vi una vez una lámina magnífica... Mi dibujo no representaba un sombrero... Las personas mayores me aconsejaron dejar a un lado los dibujos...",
      "char_start": 0,
      "char_end": 245
    },
    {
      "id": 2,
      "section_ids": [2],
      "text": "Viví así solo, sin nadie con quien poder hablar verdaderamente...",
      "char_start": 247,
      "char_end": 320
    }
  ]
}
```

---

## Metadatos

```json
{
  "title": "El Principito",
  "author": "Antoine de Saint-Exupéry",
  "publication_year": 1943
}
```

Son los únicos metadatos obligatorios del MVP.

---

## Secciones y checkpoints

Una sección es una unidad narrativa y pedagógica.

```json
{
  "id": 1
}
```

No se necesita guardar `start_block_id` ni `end_block_id` dentro de las secciones.

El inicio y final de una sección se infieren con el `section_id` de los bloques.

```text
block 4 → section_id: 1
block 5 → section_id: 1
block 6 → section_id: 2
```

El checkpoint aparece entre el último bloque de una sección y el primer bloque de la siguiente.

```text
block 5
↓
checkpoint de section 1
↓
block 6
```

Un checkpoint puede ocurrir dentro de un mismo chunk. Eso es válido.

```text
chunk 1:
block 4 → section 1
block 5 → section 1
checkpoint
block 7 → section 2
```

### Regla para materializar checkpoints

Dentro de la parte narrativa, todos los bloques visibles deben pertenecer a una sección, incluyendo:

```text
Títulos de capítulos
Subtítulos
Párrafos
Diálogos
Separadores visuales
```

Los bloques con `section_id: null` se usan solo para contenido global fuera de la lectura narrativa:

```text
Portada
Índice
Créditos
Notas editoriales
```

El frontend detecta un checkpoint cuando el bloque siguiente pertenece a otra sección narrativa.

```text
block.section_id !== nextBlock.section_id
```

Debe ignorar cambios donde uno de los dos bloques tenga `section_id: null`.

### Reglas de secciones

* Las secciones se definen después de dividir los bloques necesarios.
* Un bloque pertenece como máximo a una sección.
* Los bloques globales fuera de lectura tienen `section_id: null`.
* Si un checkpoint cae dentro de un bloque, el bloque debe dividirse antes de asignar secciones.
* Una sección puede estar repartida entre varios chunks.
* Un checkpoint no obliga a cerrar un chunk.

Ejemplo de división:

```html
<p>El niño abrió la carta. Dentro encontró una fotografía antigua.</p>
```

Si el checkpoint ocurre después de la primera oración, el bloque se convierte en:

```html
<p>El niño abrió la carta.</p>
```

```html
<p>Dentro encontró una fotografía antigua.</p>
```

Después de la división, cada bloque recibe su `section_id`.

---

## Bloques

Un bloque es una unidad visible del libro.

Puede representar un título, párrafo, diálogo, índice, separador, imagen o crédito.

```json
{
  "id": 4,
  "section_id": 1,
  "content": "<p>Cuando yo tenía seis años...</p>",
  "chunk_id": 1
}
```

No necesita un campo `type`, porque la semántica se encuentra dentro del HTML de `content`.

### Reglas de bloques

* Los bloques están en orden de lectura.
* `id` es autoincremental y representa el orden visual.
* `content` contiene HTML pequeño y sanitizado.
* Los bloques narrativos tienen `chunk_id`.
* Los bloques visibles que no entran al RAG tienen `chunk_id: null`.
* Los títulos pueden pertenecer a una sección aunque tengan `chunk_id: null`.
* Un bloque narrativo apunta a un solo chunk.
* Un bloque puede dividirse si un checkpoint o límite narrativo cae dentro de él.

Etiquetas permitidas inicialmente:

```text
p
h1
h2
h3
em
strong
br
hr
blockquote
nav
```

---

## Chunks

Un chunk es una unidad de texto limpio usada por el RAG.

```json
{
  "id": 1,
  "section_ids": [1, 2],
  "text": "Cuando yo tenía seis años...",
  "char_start": 0,
  "char_end": 245
}
```

La relación bloque → chunk se infiere de `blocks[].chunk_id`.  El
`chunk_id` de cada bloque es el `id` del chunk que lo contiene.

`section_ids` contiene los IDs únicos de las secciones narrativas presentes en el chunk, respetando el orden de lectura.

```json
{
  "section_ids": [1, 2]
}
```

No se incluye `null` dentro de `section_ids`.

### Reglas de chunks

* `id` es autoincremental dentro del libro.
* Los chunks siguen el orden de lectura.
* Un chunk agrupa uno o más bloques narrativos completos.
* Un chunk puede contener bloques de una o más secciones.
* Los chunks pueden cruzar checkpoints.
* `section_ids` se deriva de los bloques narrativos incluidos.
* En el MVP, los chunks no tienen overlap persistente.
* El texto del chunk no contiene HTML.
* Una vez publicado el libro, no se renumeran IDs existentes.

---

## Estrategia de chunking

El chunking no se ajusta obligatoriamente a los checkpoints.

Los checkpoints sirven para la experiencia pedagógica; los chunks sirven para mantener contexto suficiente para retrieval.

```text
Objetivo: 220–320 tokens
Mínimo recomendado: 80–120 tokens
Máximo normal: 400 tokens
Máximo flexible: 500 tokens
```

Reglas:

```text
1. Recorrer los bloques narrativos en orden de lectura.
2. Agregar bloques completos al chunk actual.
3. Cerrar en límites naturales: final de párrafo, diálogo, acción o escena.
4. Intentar mantener el tamaño objetivo.
5. Permitir superar ligeramente el máximo para evitar una cola demasiado pequeña.
6. No crear automáticamente chunks de una palabra, una oración mínima o un carácter.
7. No usar overlap persistente entre chunks.
8. No cerrar un chunk únicamente porque apareció un checkpoint.
```

Si un bloque aislado supera el máximo flexible, se puede dividir por oración o diálogo antes de asignarlo a un chunk.

---

## Control anti-spoiler

El RAG busca con chunks, pero el control exacto de lectura ocurre a nivel de bloques.

Ejemplo:

```text
Chunk 7:
- block 20 → section 3
- checkpoint
- block 21 → section 4
- block 22 → section 4

Alumno actualmente:
- block 20
```

Aunque el chunk 7 tenga contenido de la sección 4, no se puede recuperar ni entregar completo mientras el alumno siga en el bloque 20.

Los chunks completos disponibles para búsqueda deben cumplir:

```text
chunk.end_block_id <= current_block_id
```

El backend debe construir el contexto así:

```text
1. Recuperar por similitud solo chunks completos ya leídos.

2. Priorizar chunks cuya section_ids incluya current_section_id.

3. Identificar el chunk actual.

4. Construir un fragmento parcial del chunk actual usando únicamente
   bloques narrativos con:

   block.chunk_id == current_chunk_id
   block.id <= current_block_id

5. Enviar al LLM:
   - fragmento visible del chunk actual;
   - chunks anteriores relevantes;
   - pregunta del alumno.
```

Ejemplo:

```text
Contexto actual visible:
texto de block 20

Contexto anterior relevante:
chunks completamente leídos recuperados por RAG

Pregunta:
¿Por qué el personaje reaccionó así?
```

Los bloques posteriores a `current_block_id` nunca se entregan al LLM.

### Consulta mientras el bloque actual no tiene `chunk_id`

Un título o separador puede tener:

```json
{
  "chunk_id": null
}
```

En ese caso, el frontend puede enviar `current_chunk_id: null`.

El backend debe usar:

* los chunks completamente leídos;
* los bloques narrativos visibles anteriores;
* el contenido del bloque actual solo si aporta contexto.

---

## Offsets por caracteres

`char_start` y `char_end` se calculan sobre un texto canónico.

```text
Texto canónico:
- solo texto narrativo;
- sin HTML;
- sin índice, portada, créditos ni notas editoriales;
- en orden de lectura;
- separado entre chunks por "\n\n".
```

Convención:

```text
char_start → inclusivo
char_end   → exclusivo
```

Ejemplo:

```python
chunk_text = canonical_text[char_start:char_end]
```

Los offsets no se calculan sobre el HTML del reader.

---

## Relación entre bloques, secciones y chunks

```text
Sección 1
  block 3 → título
  block 4 ─┐
           ├── chunk 1
  block 5 ─┘
  checkpoint

Sección 2
  block 6 → título
  block 7 ─┘  chunk 1 continúa
  block 8 ──── chunk 2
```

---

## Contexto enviado desde frontend

Cuando el alumno consulta, el frontend debe enviar:

```json
{
  "book_id": "el_principito_es",
  "current_section_id": 1,
  "current_block_id": 4,
  "current_chunk_id": 1,
  "question": "¿Por qué el narrador dejó de dibujar?"
}
```

`current_block_id` es obligatorio para evitar spoilers dentro del chunk actual.

`current_chunk_id` puede ser `null` cuando el bloque visible actual no pertenece a un chunk narrativo.
