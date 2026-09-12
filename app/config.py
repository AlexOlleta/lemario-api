"""Configuración centralizada (cargada desde entorno / .env)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEMARIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Desactiva el parseo JSON automático de campos lista: los leemos
        # como CSV en _split_csv (p. ej. LEMARIO_API_KEYS=a,b,c).
        enable_decoding=False,
    )

    # Storage
    database_path: str = "data/lemario.db"

    # Security
    api_keys: list[str] = []
    api_key_header: str = "X-API-Key"

    # Rate limiting
    rate_limit_default: str = "120/minute"
    rate_limit_definitions: str = "30/minute"
    # /words/exists es local (sin red): puede ser mucho más generoso.
    rate_limit_exists: str = "600/minute"

    # CORS
    cors_origins: list[str] = ["*"]

    # External sources
    rae_api_base: str = "https://rae-api.com/api/words"
    dle_base: str = "https://dle.rae.es"
    http_timeout: float = 10.0
    http_retries: int = 2

    # Source word list
    list_repo: str = "rubenperezm/ListadosPalabrasRAE"
    list_branch: str = "main"

    # CREA frequency list (RAE, CC BY-SA 4.0). Local file: the RAE publishes
    # it for download, so it is not fetched automatically.
    crea_path: str = "data/crea_lemas.txt"

    # Frequency list (scripts/enrich_frequency.py). OpenSubtitles 2018,
    # CC BY-SA 3.0: https://github.com/hermitdave/FrequencyWords
    freq_list_url: str = (
        "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
        "master/content/2018/es/es_full.txt"
    )

    @field_validator("api_keys", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Permite definir listas como CSV en variables de entorno."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def security_enabled(self) -> bool:
        return bool(self.api_keys)


@lru_cache
def get_settings() -> Settings:
    return Settings()
