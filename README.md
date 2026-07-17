# 📖 Reading Companion

**Un compañero de lectura conversacional para escolares que sabe exactamente hasta dónde has leído — y no te revienta el final.**

<sub>An agentic, retrieval-augmented reading companion for secondary-school students. It answers doubts about the book, quizzes comprehension with non-punitive feedback, and — its core contribution — gates every response by the reader's progress so it can never spoil what's ahead.</sub>

<p>
<img alt="status" src="https://img.shields.io/badge/estado-prototipo%20acad%C3%A9mico-blueviolet">
<img alt="python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white">
<img alt="fastapi" src="https://img.shields.io/badge/API-FastAPI%20%2B%20SSE-009688?logo=fastapi&logoColor=white">
<img alt="rag" src="https://img.shields.io/badge/RAG-E5%20%2B%20ChromaDB-orange">
<img alt="license" src="https://img.shields.io/badge/licencia-MIT-green">
</p>

**▶️ [Ver la demo en vídeo](https://youtu.be/6d9IIVmy-bo)**

---

## El problema

Miles de escolares leen su **Plan Lector** solos, sin nadie a quien preguntarle una
duda en el momento exacto en que aparece. Un asistente genérico con el PDF pegado no
sirve: no tiene idea de por dónde va el estudiante, le arruina el final del libro a la
primera pregunta, y no ofrece ninguna forma de comprobar si de verdad entendió.

Este proyecto es un agente que **es consciente de la posición del lector dentro de la
obra** y adapta todo su comportamiento a ella.

## Qué hace

- 💬 **Responde dudas** sobre la obra con RAG, devolviendo las **citas exactas** (con offsets de carácter) para que el estudiante pueda ir al pasaje y comprobarlo.
- 🚩 **Le pregunta a él.** En puntos marcados del texto ("banderas") lanza una pregunta de comprensión y evalúa la respuesta con **retroalimentación formativa, nunca una nota**. El objetivo es retención: detenerse, verbalizar y consolidar.
- 🎨 **Ilustra** el pasaje que se está leyendo, para anclar la escena visualmente.
- 🧑‍🤝‍🧑 **Muestra las entidades** (personajes y lugares) que aparecen en el tramo actual.

## 🛡️ Lo que lo hace distinto: anti-spoiler estructural

El avance de lectura se calcula en el frontend y se expresa como un **índice monótono
sobre los chunks** de la obra. La barrera no es una súplica al modelo ("por favor no
hagas spoilers") — se aplica **en la capa de recuperación**: el sistema *no puede
recuperar* un fragmento por encima del progreso del lector. No decide callarlo; es que
no lo tiene delante. Es una restricción imposible de saltar, no una instrucción.

> Adaptación original a un contexto educativo de la investigación en detección de
> spoilers (Tran et al., *Spoiler Detection as Semantic Text Matching*, EMNLP 2023).

## Arquitectura

**Router + herramientas.** Un modelo pequeño y barato clasifica; un modelo grande genera.

```
        mensaje del estudiante
                 │
        ┌────────▼─────────┐     Router (Llama 3.1 8B, temp 0)
        │  clasificación   │     → 5 intenciones, o salto directo
        └────────┬─────────┘        a evaluación si hay bandera pendiente
                 │
   ┌──────┬──────┼───────┬──────────┐
   ▼      ▼      ▼       ▼          ▼
 QA-RAG  Eval  Imagen  Resumen*  Grafo*     (*stubs declarados)
   │      │
   └──────┴──► Contenido: modelo grande (proveedor configurable por rol)
```

- **Proveedor de LLM configurable por rol** (`router` / `content` / `visual_planner`):
  el enrutado corre en un 8B gratis mientras el contenido usa un modelo mejor, sin pagar
  de más. Backends soportados: NVIDIA NIM, OpenAI, Anthropic, Gemini.
- El **motor de recuperación** usa un *chunker consciente de bloques narrativos*
  (no trocea escenas a tamaño fijo), embeddings **multilingual-e5-base** y **ChromaDB**.

## Corpus

Ocho obras del Plan Lector peruano, preprocesadas con un pipeline propio.

| Métrica | Total |
|---|---|
| Obras | 8 |
| Chunks recuperables | 2 353 |
| Preguntas de comprensión embebidas | 392 |
| Bloques narrativos | 12 593 |
| Tamaño medio de chunk | ~410 tokens (0 truncados) |

<sub>Crónica de una muerte anunciada · El maravilloso mago de Oz · El viejo y el mar ·
La ciudad y los perros · La metamorfosis · Las aventuras de Tom Sawyer · Matalaché ·
Viaje al centro de la Tierra.</sub>

## Stack

`Python 3.10+` · `FastAPI` + Server-Sent Events · `sentence-transformers` (E5) ·
`ChromaDB` · `spaCy` (NER) · frontend en React/Vercel · difusión vía Cloudflare Workers AI.

## Inicio rápido

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev,ner]"   # Windows
```

Configura las credenciales en un `.env` (esquema completo en `src/companion/config.py`):

```dotenv
LLM_PROVIDER=nvidia
NVIDIA_API_KEY=...
# Opcional: proveedor y modelo por rol
CONTENT_PROVIDER=openai
CONTENT_MODEL=...
```

Levanta la API:

```bash
uvicorn companion.api.server:app --port 8000
```

## Estructura

```
src/companion/
  corpus/         carga y normalización canónica del texto
  chunkers/       segmentación narrativa con offsets absolutos
  embedders/      embeddings E5 locales (sin API key)
  vector_store/   ChromaDB persistente
  retrieval/      retriever + reranker + gate anti-spoiler
  enrichers/      enriquecimiento de chunks para el embedding
  providers/      LLM y NER detrás de interfaces (nvidia/openai/anthropic/gemini)
  scope/          ScopeResolver (selección determinista de chunks)
  agent/          router + tools + estado
  visual_support/ planificador de escenas + prompt builder de ilustración
  images/         proveedores de generación de imágenes
  analysis/       extracción de elementos narrativos (NER)
  jobs/           indexación, NER, grafo
  api/            FastAPI (chat SSE, imágenes async, libros)
```

## Documentación

- ▶️ **[Vídeo demo (YouTube)](https://youtu.be/6d9IIVmy-bo)** — el sistema funcionando de punta a punta.
- 📄 **[Informe académico (PDF)](docs/Informe_Grupo_8.pdf)** — metodología y resultados de las pruebas con usuarios (*n=6*).
- 🖥️ **[Presentación (PDF)](<docs/Companero-de-Lectura-un-agente-RAG-que-sabe-por-donde-vas.pptx.pdf>)** — la charla final.
- 🗂️ **[`agent_log/`](agent_log/)** — bitácora de desarrollo: 28 entradas, decisiones de diseño y análisis de causa raíz. La historia real del proyecto está aquí.
- 🤝 **[`AGENTS.md`](AGENTS.md)** — contratos que no se rompen y convenciones de trabajo en equipo.

## Estado y despliegue

Prototipo académico. **No está en producción.** El frontend estático queda alojado en
Vercel; el backend corre localmente y se expone puntualmente a través de un túnel solo
para demos. Sin URL permanente ni controles de acceso de nivel producción — por diseño.

## Equipo

Trabajo del **Grupo 8**, Pontificia Universidad Católica del Perú (PUCP):
Giano Montaño · Brayan Ávila · Aaron Arana · Rodrigo Chang · Erick Olivares.

Desarrollado de forma incremental y coordinado mediante handoffs escritos entre cinco
desarrolladores y sus agentes de terminal (ver [`agent_log/`](agent_log/)).

## Licencia

Publicado bajo licencia **[MIT](LICENSE)** © 2026 Grupo 8 (PUCP). Puedes usar, copiar,
modificar y distribuir el código libremente, manteniendo el aviso de copyright.
