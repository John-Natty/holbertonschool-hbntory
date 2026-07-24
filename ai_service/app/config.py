"""Configuration du service IA HBntory."""

from functools import lru_cache
import math
from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    Field,
    StringConstraints,
    field_validator,
)
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

PositiveFiniteFloat = Annotated[
    float,
    Field(gt=0, allow_inf_nan=False),
]

PositiveInt = Annotated[
    int,
    Field(gt=0),
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
    mcp_request_timeout_seconds: PositiveFiniteFloat = 10.0
    mcp_max_concurrent_calls: PositiveInt = 10

    @field_validator(
        "mcp_request_timeout_seconds",
        mode="before",
    )
    @classmethod
    def reject_boolean_timeout(cls, value: object) -> object:
        """Refuse un booléen utilisé comme durée."""

        if isinstance(value, bool):
            raise ValueError(
                "Le délai MCP doit être un nombre strictement positif."
            )

        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(
                "Le délai MCP doit être un nombre fini."
            )

        return value

    @field_validator(
        "mcp_max_concurrent_calls",
        mode="before",
    )
    @classmethod
    def reject_boolean_concurrency(cls, value: object) -> object:
        """Refuse un booléen utilisé comme limite de concurrence."""

        if isinstance(value, bool):
            raise ValueError(
                "La concurrence MCP doit être un entier positif."
            )

        return value


@lru_cache
def get_settings() -> Settings:
    """Charge une seule fois la configuration depuis l'environnement."""

    return Settings()
