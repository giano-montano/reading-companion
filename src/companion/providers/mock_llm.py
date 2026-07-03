from __future__ import annotations
from rag.providers.llm_base import LLMProvider

# Canned JSON returned for hypothetical-questions prompts.
_MOCK_QUESTIONS_JSON = (
    '["¿Cuál es el nombre del protagonista de este fragmento?", '
    '"¿Dónde transcurre la acción descrita en este pasaje?", '
    '"¿Qué ocurre en esta escena y qué consecuencias tiene?", '
    '"¿Cómo reacciona el personaje principal ante los eventos narrados?"]'
)

_MOCK_SUMMARY_ES = (
    "En este fragmento de la obra, el narrador describe los eventos principales "
    "de la escena con los personajes característicos de la narrativa española."
)

_MOCK_ANSWER_ES = (
    "Según el contexto proporcionado, la respuesta se relaciona con los temas "
    "centrales de la obra: sus personajes, sus acciones y el ambiente en que "
    "se desarrollan. "
    "[MockLLMProvider — reemplaza por un proveedor real para una respuesta fundamentada.]"
)


class MockLLMProvider(LLMProvider):
    """
    Deterministic canned outputs.  No API key required.

    Detection order uses UNIQUE strings from each prompt template so there is
    no false-positive between prompts that share common Spanish vocabulary.
    """

    def complete(self, prompt: str) -> str:
        p = prompt.lower()

        # Questions prompt — unique markers: "array json" or "devuelve únicamente"
        if "array json" in p or "devuelve únicamente" in p or "devuelve unicamente" in p:
            return _MOCK_QUESTIONS_JSON

        # Summary/context prompt — unique markers: "descripción contextual" or "sitúen"
        if "descripción contextual" in p or "descripcion contextual" in p or "sitúen" in p or "situen" in p:
            return _MOCK_SUMMARY_ES

        # English question-generation prompts (backward compat with existing tests)
        if "question" in p and "chunk" in p:
            return (
                "¿Cuál es el concepto principal discutido en este pasaje?\n"
                "¿Cómo se relaciona este tema con la recuperación de información?\n"
                "¿Qué aplicaciones prácticas describe este contenido?"
            )

        # English summary prompts (backward compat)
        if ("summar" in p or "one-sentence" in p or "one sentence" in p) and "chunk" in p:
            return _MOCK_SUMMARY_ES

        # Generation prompts
        if "answer:" in p or "responde" in p or "pregunta:" in p or "question:" in p:
            return _MOCK_ANSWER_ES

        return "[MockLLMProvider] respuesta genérica de prueba."

    def chat(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        return self.complete(last)
