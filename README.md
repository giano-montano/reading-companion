# reading-companion

Compañero de lectura agéntico (RAG) para alumnos de secundaria. Acompaña al
alumno mientras lee un texto narrativo: resume lo que ve, responde preguntas
sobre la obra, muestra el grafo de personajes y evalúa la participación en
preguntas de comprensión. Dos modelos Llama en NVIDIA NIM: un **router 8B** que
clasifica la intención y un **content 70B** que genera las respuestas.

> Estado: en construcción (Fase 2). Infraestructura RAG migrada de F1; agente
> (router, scope, tools, API) en desarrollo incremental.

## Inicio rápido

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev,ner]"   # Windows
```

Configura credenciales en un `.env` (ver `src/companion/config.py`):

```
llm_provider=nvidia
nvidia_api_key=...
```

## Estructura

```
src/companion/
  corpus/        carga y normalización canónica del texto
  chunkers/      segmentación en chunks con offsets absolutos
  embedders/     embeddings locales (multilingüe, sin API key)
  vector_store/  ChromaDB persistente
  retrieval/     retriever + reranker
  enrichers/     enriquecimiento de chunks para el embedding
  providers/     LLM y NER detrás de ABCs
  scope/         ScopeResolver (selección determinista de chunks)
  agent/         router + tools + estado
  jobs/          indexación, NER, grafo
  api/           FastAPI
```

## Para desarrolladores y sus agentes

- **[`AGENTS.md`](AGENTS.md)** — reglas de trabajo, contratos que no se rompen,
  convenciones y coordinación de equipo.
- **[`agente_log/`](agente_log/)** — registro de sesiones: decisiones, diseño y
  puntos de cableado abiertos. Léelo antes de contribuir.
