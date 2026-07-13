from __future__ import annotations
from companion.providers.llm_base import LLMProvider
from companion.config import settings


def _build_role_llm(role: str, model: str, temperature: float) -> LLMProvider:
    """
    Build a role-specific LLM (router | content) honoring settings.llm_provider.

    Contract #3: router and content NEVER share a cache instance — the cache tag
    embeds the role, so their responses can never collide even on the same model.
    Mock is returned uncached (already deterministic and free).
    """
    if settings.llm_provider == "nvidia":
        from companion.providers.nvidia_llm import NvidiaLLMProvider
        provider: LLMProvider = NvidiaLLMProvider(model=model, temperature=temperature)
        tag = f"nvidia:{role}:{model}"

    elif settings.llm_provider == "gemini":
        from companion.providers.gemini_llm import GeminiProvider
        provider = GeminiProvider(model=settings.gemini_model)
        tag = f"gemini:{role}:{settings.gemini_model}"

    elif settings.llm_provider == "anthropic":
        from companion.providers.anthropic_llm import AnthropicLLMProvider
        provider = AnthropicLLMProvider(model=settings.llm_model)
        tag = f"anthropic:{role}:{settings.llm_model}"

    else:
        from companion.providers.mock_llm import MockLLMProvider
        return MockLLMProvider()  # mock: skip cache, already deterministic

    if settings.llm_cache_enabled:
        from companion.providers.llm_cache import CachingLLMProvider
        return CachingLLMProvider(
            provider,
            cache_dir=settings.llm_cache_dir,
            provider_tag=tag,
        )
    return provider


def get_router_llm() -> LLMProvider:
    """Modelo ligero para clasificar intención (8B). Temperatura 0."""
    return _build_role_llm("router", settings.router_model, temperature=0.0)


def get_content_llm() -> LLMProvider:
    """Modelo pesado para generar contenido (70B). Temperatura 0.2."""
    return _build_role_llm("content", settings.content_model, temperature=0.2)


def get_visual_planner_llm() -> LLMProvider:
    """Modelo ligero (8B) que destila el extracto en escenas visuales antes de
    llamar al generador de imágenes. Rol propio → cache aparte (contrato #3)."""
    return _build_role_llm("visual", settings.visual_planner_model, temperature=0.3)


def get_llm_provider(cached: bool | None = None) -> LLMProvider:
    """
    Build the configured LLM provider.
    Wraps real providers with CachingLLMProvider unless the caller opts out.
    Mock is never cached (it's already free and deterministic).
    """
    if settings.llm_provider == "anthropic":
        from companion.providers.anthropic_llm import AnthropicLLMProvider
        provider: LLMProvider = AnthropicLLMProvider(model=settings.llm_model)
        model_name = settings.llm_model

    elif settings.llm_provider == "gemini":
        from companion.providers.gemini_llm import GeminiProvider
        provider = GeminiProvider(model=settings.gemini_model)
        model_name = settings.gemini_model

    elif settings.llm_provider == "nvidia":
        from companion.providers.nvidia_llm import NvidiaLLMProvider
        provider = NvidiaLLMProvider(model=settings.nvidia_model)
        model_name = settings.nvidia_model
    else:
        from companion.providers.mock_llm import MockLLMProvider
        return MockLLMProvider()   # mock: skip cache, already deterministic

    # Wrap real providers with disk cache (respects llm_cache_enabled setting)
    use_cache = settings.llm_cache_enabled if cached is None else cached
    if use_cache:
        from companion.providers.llm_cache import CachingLLMProvider
        return CachingLLMProvider(
            provider,
            cache_dir=settings.llm_cache_dir,
            provider_tag=f"{settings.llm_provider}:{model_name}",
        )
    return provider

