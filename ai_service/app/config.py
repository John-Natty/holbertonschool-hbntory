"""Configuration du service IA HBntory."""

from functools import lru_cache
from typing import Annotated

from pydantic import AnyHttpUrl, Field, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict


NonEmptyString = Annotated[
    str,
    Field(strict=True),
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]

ServicePort = Annotated[
    int,
    Field(ge=1, le=65535),
]


class Settings(BaseSettings):
    """Regroupe les paramètres nécessaires au service IA."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=None,
        extra="forbid",
    )

    ai_service_host: NonEmptyString = "0.0.0.0"
    ai_service_port: ServicePort = 8001
    mcp_server_url: AnyHttpUrl = (
        "http://product-mcp-server:8000/mcp"
    )


@lru_cache
def get_settings() -> Settings:
    """Charge une seule fois la configuration depuis l'environnement."""

    return Settings()
