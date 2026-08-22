from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration, sourced from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # OpenRouteService
    ors_api_key: str = "changeme"
    ors_base_url: str = "https://api.openrouteservice.org"

    # Geoapify
    geoapify_api_key: str = "changeme"
    geoapify_base_url: str = "https://api.geoapify.com"

    # LLM
    llm_provider: Literal["openai", "gemini"] = "openai"
    openai_api_key: str = "changeme"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = "changeme"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-1.5-flash"

    # HTTP
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 2

    @property
    def has_live_ors(self) -> bool:
        return self.ors_api_key not in ("", "changeme")

    @property
    def has_live_geoapify(self) -> bool:
        return self.geoapify_api_key not in ("", "changeme")

    @property
    def has_live_llm(self) -> bool:
        key = self.openai_api_key if self.llm_provider == "openai" else self.gemini_api_key
        return key not in ("", "changeme")


@lru_cache
def get_settings() -> Settings:
    return Settings()
