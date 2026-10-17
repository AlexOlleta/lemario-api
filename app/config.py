"""Configuración centralizada (cargada desde entorno / .env)."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEMARIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Las listas se leen como CSV (_split_csv), no como JSON.
        enable_decoding=False,
    )

    environment: Literal["development", "production"] = "development"

    database_path: str = "data/lemario.db"

    api_keys: list[str] = []
    api_key_header: str = "X-API-Key"
    trusted_networks: list[str] = ["127.0.0.0/8", "::1/128"]

    rate_limit_default: str = "120/minute"
    rate_limit_definitions: str = "30/minute"
    rate_limit_exists: str = "600/minute"
    rate_limit_storage: str = "memory://"

    cors_origins: list[str] = ["*"]

    rae_api_base: str = "https://rae-api.com/api/words"
    dle_base: str = "https://dle.rae.es"
    http_timeout: float = 10.0
    http_retries: int = 2

    list_repo: str = "rubenperezm/ListadosPalabrasRAE"
    list_branch: str = "379aec4fdfe9c4d678b435a0772b59649693a6a3"

    crea_path: str = "data/crea_lemas.txt"
    freq_list_url: str = (
        "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
        "master/content/2018/es/es_full.txt"
    )

    @field_validator("api_keys", "cors_origins", "trusted_networks", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("trusted_networks")
    @classmethod
    def _check_networks(cls, value: list[str]) -> list[str]:
        for network in value:
            ipaddress.ip_network(network, strict=False)
        return value

    @model_validator(mode="after")
    def _check_production(self) -> Settings:
        if self.environment != "production":
            return self
        problems = []
        if not self.api_keys:
            problems.append("LEMARIO_API_KEYS está vacío (la API quedaría abierta)")
        if "*" in self.cors_origins:
            problems.append("LEMARIO_CORS_ORIGINS no puede ser '*'")
        if problems:
            raise ValueError("Configuración insegura para producción: " + "; ".join(problems))
        return self

    @property
    def security_enabled(self) -> bool:
        return bool(self.api_keys)

    @property
    def trusted_nets(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        return [ipaddress.ip_network(n, strict=False) for n in self.trusted_networks]


@lru_cache
def get_settings() -> Settings:
    return Settings()
