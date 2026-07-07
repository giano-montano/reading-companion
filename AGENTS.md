# AGENTS.md

Guía para agentes de terminal (Claude Code, etc.) que trabajan en este repo.
Es un equipo: varias personas y sus agentes tocan el mismo código. Lee esto
entero antes de escribir código, y sigue las reglas de coordinación.

## Qué es esto

Compañero de lectura agéntico (RAG) para alumnos de secundaria. El alumno lee un
texto narrativo y le pide cosas al agente por chat: resumir, preguntar sobre la
obra, ver el grafo de personajes, o responder una pregunta de comprensión.
Dos LLM en NVIDIA NIM: **router 8B** (clasifica intención) + **content 70B**
(genera contenido). Detalle de producto y arquitectura: ver `agent_log/`.

## 📌 Empieza aquí: registro de sesiones (`agent_log/`)

**Antes de tocar nada, lee el handoff más reciente en `agent_log/`.** Es la
fuente de verdad viva de decisiones, diseño, tensiones y puntos de cableado
abiertos. Está por encima de cualquier suposición sacada del código.

- Handoff actual: [`agent_log/2026-07-05-preprocessing-pipeline.md`](agent_log/2026-07-05-preprocessing-pipeline.md)
- **Si cambias un contrato o tomas una decisión de arquitectura, escríbela en un
  handoff nuevo (o actualiza el vigente) EN EL MISMO COMMIT.** Un cambio de
  contrato sin registro es un bug para el resto del equipo.

## Setup

```bash
python -m venv .venv
# Windows:
.venv/Scripts/python.exe -m pip install -e ".[dev,ner]"
```
El intérprete del proyecto es `.venv/Scripts/python.exe` (Windows). El código
vive en `src/` (layout src; `pip install -e` lo pone en el path).

## Build / test / lint

```bash
.venv/Scripts/python.exe -m pytest        # tests (aún no hay suite; ver handoff §7)
.venv/Scripts/python.exe -m ruff check src # lint (line-length 100, py310)
```

## Contratos que NUNCA se rompen

1. **Texto canónico.** Lo produce `build_canonical_text()` en
   `corpus/canonical_text.py` (= `"\n\n".join(chunk.text)` en orden de lectura)
   y es idéntico al que renderiza el frontend. Una sola normalización. Nunca
   dos. Offsets con `recompute_offsets()`, verificables con `validate_offsets()`.
2. **Offsets absolutos.** `char_start`/`char_end` sobre ese string canónico,
   persistidos en Chroma. Leer con `int(meta.get("char_start", 0))`.
3. **Dos LLM, dos providers.** `get_router_llm()` (8B, temp 0) y
   `get_content_llm()` (70B) con tags de cache distintos. Nunca compartir
   instancia.
4. **El agente es fracción del producto.** Panel NER y estado de lectura (scroll,
   progreso) son eventos del frontend, no pasan por el LLM. No sobredimensionar.

## Convenciones de código

- Python ≥3.10, `from __future__ import annotations` en cada módulo.
- Contratos de datos con **pydantic v2** (`BaseModel`, `Field`). Ver
  `src/companion/schemas.py` y `src/companion/agent/tools/contracts.py`.
- Nada de nombres de modelo hard-coded en la lógica: todo en `config.py`
  (pydantic-settings, `.env`).
- Providers detrás de ABCs (`LLMProvider`, `Embedder`, `VectorStore`, ...).
  Inyecta dependencias por constructor; no instancies dentro de la lógica.
- Comentarios y texto de cara al alumno en español.

## Coordinación de equipo

- **Dueños por área** (evita pisarse):
  - Chunking, `NarrativeChunker`, QA-RAG, retrieval → **Chang**.
  - Contratos de tools, ScopeResolver, Router, orquestador → **Giano**.
- Trabaja en tu rama; `main` es estable. Rama de integración: `dev`.
- **Antes de editar `contracts.py` o `schemas.py`** (superficie compartida):
  avisa y escribe el cambio en `agent_log/`. Un rename de campo se coordina en
  un solo commit con todos los consumidores.
- Haz cambios pequeños y verificables. Al terminar una pieza, deja un handoff.

## No hagas

- No cambies la normalización del texto canónico (rompe todos los offsets).
- No compartas una instancia de LLM entre router y content.
- No metas el estado de lectura ni el panel NER a través del LLM.
- No implementes piezas que no se te pidieron; ante decisión abierta, pregunta y
  déjala anotada en `agent_log/`.
