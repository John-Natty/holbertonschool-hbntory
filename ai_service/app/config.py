"""Configuration du service IA HBntory."""

from functools import lru_cache
import math
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

NonNegativeFiniteFloat = Annotated[
    float,
    Field(ge=0, allow_inf_nan=False),
]

PositiveInt = Annotated[
    int,
    Field(gt=0),
]

CorsOriginList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    """Regroupe les paramètres nécessaires au service IA."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=None,
        extra="forbid",
    )

    ai_service_host: NonEmptyString = "0.0.0.0"
    ai_service_port: ServicePort = 8001
    cors_allowed_origins: CorsOriginList = [
        "http://localhost:8080",
    ]
    mcp_server_url: AnyHttpUrl = (
        "http://product-mcp-server:8000/mcp"
    )
    mcp_request_timeout_seconds: PositiveFiniteFloat = 10.0
    mcp_max_concurrent_calls: PositiveInt = 10
    mcp_reconnect_attempts: PositiveInt = 3
    mcp_reconnect_initial_delay_seconds: NonNegativeFiniteFloat = 0.25
    mcp_reconnect_max_delay_seconds: NonNegativeFiniteFloat = 2.0
    ai_intent_provider: Literal["rules", "ollama"] = "rules"
    ollama_base_url: AnyHttpUrl = "http://ollama:11434"
    ollama_model: NonEmptyString = "gemma3:latest"
    ollama_request_timeout_seconds: PositiveFiniteFloat = 30.0

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def validate_cors_allowed_origins(
        cls,
        value: object,
    ) -> list[str]:
        """Normalise et valide une liste non vide d'origines HTTP."""

        if isinstance(value, str):
            raw_origins: object = value.split(",")
        else:
            raw_origins = value

        if not isinstance(raw_origins, (list, tuple)):
            raise ValueError(
                "Les origines CORS doivent former une liste."
            )

        origins: list[str] = []

        for raw_origin in raw_origins:
            if not isinstance(raw_origin, str):
                raise ValueError(
                    "Chaque origine CORS doit être une chaîne."
                )

            origin = raw_origin.strip()

            if not origin:
                raise ValueError(
                    "La liste des origines CORS ne peut pas être vide."
                )

            parsed = urlsplit(origin)

            try:
                port = parsed.port
            except ValueError as error:
                raise ValueError(
                    "Chaque origine CORS doit avoir un port valide."
                ) from error

            if (
                parsed.scheme.lower() not in {"http", "https"}
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "Chaque origine CORS doit être une origine HTTP "
                    "sans chemin, identifiants, requête ni fragment."
                )

            hostname = parsed.hostname.lower()

            if ":" in hostname:
                hostname = f"[{hostname}]"

            normalized_origin = (
                f"{parsed.scheme.lower()}://{hostname}"
            )

            if port is not None:
                normalized_origin += f":{port}"

            if normalized_origin not in origins:
                origins.append(normalized_origin)

        if not origins:
            raise ValueError(
                "La liste des origines CORS ne peut pas être vide."
            )

        return origins

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
        "mcp_reconnect_attempts",
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

    @field_validator(
        "mcp_reconnect_initial_delay_seconds",
        "mcp_reconnect_max_delay_seconds",
        mode="before",
    )
    @classmethod
    def reject_invalid_reconnect_delay(
        cls,
        value: object,
    ) -> object:
        """Refuse une durée de reconnexion booléenne ou non finie."""

        if isinstance(value, bool):
            raise ValueError(
                "Le délai de reconnexion doit être un nombre positif ou nul."
            )

        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(
                "Le délai de reconnexion doit être un nombre fini."
            )

        return value

    @field_validator(
        "ollama_request_timeout_seconds",
        mode="before",
    )
    @classmethod
    def reject_invalid_ollama_timeout(
        cls,
        value: object,
    ) -> object:
        """Refuse une durée Ollama booléenne ou non finie."""

        if isinstance(value, bool):
            raise ValueError(
                "Le délai Ollama doit être un nombre positif."
            )

        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(
                "Le délai Ollama doit être un nombre fini."
            )

        return value

    @model_validator(mode="after")
    def validate_reconnect_delay_bounds(self) -> "Settings":
        """Exige un plafond supérieur ou égal au délai initial."""

        if (
            self.mcp_reconnect_max_delay_seconds
            < self.mcp_reconnect_initial_delay_seconds
        ):
            raise ValueError(
                "Le délai maximal de reconnexion doit être supérieur "
                "ou égal au délai initial."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    """Charge une seule fois la configuration depuis l'environnement."""

    return Settings()
