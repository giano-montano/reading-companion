"""
Central settings — read from .env then from environment variables.
All model names and provider choices live here; nothing is hard-coded in logic.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM — "mock" | "gemini" | "anthropic" | "nvidia"
    llm_provider: str = Field("mock")
    llm_model: str = Field("mock-model")
    anthropic_api_key: str | None = Field(None)

    # Google / Gemini
    google_api_key: str | None = Field(None)
    gemini_model: str = Field("gemini-1.5-flash")

    nvidia_api_key: str | None = Field(None)
    nvidia_model: str = Field("deepseek-ai/deepseek-v4-flash")
    nvidia_base_url: str = Field("https://integrate.api.nvidia.com/v1")

    # Image generation - Cloudflare
    cloudflare_api_token: str | None = Field(None)
    cloudflare_account_id: str | None = Field(None)
    cloudflare_image_model: str = Field("@cf/black-forest-labs/flux-2-klein-9b")

    # Visual support
    visual_output_dir: str = Field("./generated_visuals")
    visual_mock_enabled: bool = Field(False)

    router_model:  str = Field("meta/llama-3.1-8b-instruct")
    content_model: str = Field("meta/llama-3.3-70b-instruct")
    # Destila el extracto en escenas visuales antes de llamar al generador de
    # imágenes (ver visual_support/scene_planner.py). Modelo ligero a propósito.
    visual_planner_model: str = Field("meta/llama-3.1-8b-instruct")

    # LLM response cache (applies to real providers; mock is never cached)
    llm_cache_enabled: bool = Field(True)
    llm_cache_dir: str = Field("./.llm_cache")

    # Embeddings
    embedding_model: str = Field("intfloat/multilingual-e5-base")

    # NER — Spanish model by default; falls back to smaller variants automatically
    ner_model: str = Field("es_core_news_sm")

    # Vector store
    vector_store: str = Field("chroma")
    chroma_persist_dir: str = Field("./chroma_db")

    # Retrieval
    top_k: int = Field(5)

    # API / CORS — coma-separada; "*" en dev. En prod ponla al dominio del
    # frontend (p. ej. "https://tu-app.vercel.app") para no dejar el endpoint
    # abierto a cualquier origen una vez expuesto por el túnel.
    cors_allow_origins: str = Field("*")

    # # Chunking
    # chunk_size: int = Field(500)
    # chunk_overlap: int = Field(50)


settings = Settings()
