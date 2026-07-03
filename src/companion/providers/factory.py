from __future__ import annotations
from companion.providers.llm_base import LLMProvider
from companion.config import settings


def get_router_llm() -> LLMProvider:
    """Modelo ligero para clasificar intención (8B). Temperatura 0."""
    # usa settings.router_model, temperature=0.0
    
    from companion.providers.llm_cache import CachingLLMProvider
    return CachingLLMProvider(
        provider,
        cache_dir=settings.llm_cache_dir,
        provider_tag=f"nvidia:router:{settings.router_model}",
    )
    return provider
    ...  # usa settings.router_model, temperature=0.0

def get_content_llm() -> LLMProvider:
    """Modelo pesado para generar contenido (70B)."""
    # usa settings.content_model, temperature=0.2
     from companion.providers.llm_cache import CachingLLMProvider
    return CachingLLMProvider(
        provider,
        cache_dir=settings.llm_cache_dir,
        provider_tag=f"nvidia:content:{settings.content_model}",
    )


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

