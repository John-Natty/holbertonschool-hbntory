#!/usr/bin/env python3
"""Configuration du serveur MCP HBntory."""

import os
from dataclasses import dataclass
from urllib.parse import urlparse


class ConfigurationError(RuntimeError):
    """Erreur levée lorsqu'une configuration MCP est invalide."""


PLACEHOLDER_INTERNAL_API_KEYS = {
    "your_private_internal_api_key",
    "replace_with_a_random_internal_api_key",
}


@dataclass(frozen=True, slots=True)
class Settings:
    """Regroupe les paramètres nécessaires au serveur MCP."""

    product_api_base_url: str
    backoffice_internal_url: str
    internal_api_key: str
    mcp_host: str
    mcp_port: int


def load_settings() -> Settings:
    """Charge et valide la configuration depuis l'environnement."""

    product_api_base_url = _read_http_url(
        "PRODUCT_API_BASE_URL"
    )
    backoffice_internal_url = _read_http_url(
        "BACKOFFICE_INTERNAL_URL"
    )
    internal_api_key = _read_internal_api_key()

    mcp_host = os.getenv("MCP_HOST", "0.0.0.0").strip()

    if not mcp_host:
        raise ConfigurationError(
            "La variable MCP_HOST ne peut pas être vide."
        )

    mcp_port = _read_port(
        os.getenv("MCP_PORT", "8000")
    )

    return Settings(
        product_api_base_url=product_api_base_url,
        backoffice_internal_url=backoffice_internal_url,
        internal_api_key=internal_api_key,
        mcp_host=mcp_host,
        mcp_port=mcp_port,
    )


def _read_required_string(variable_name: str) -> str:
    """Retourne une variable obligatoire non vide."""

    value = os.getenv(variable_name)

    if value is None or not value.strip():
        raise ConfigurationError(
            f"La variable {variable_name} est manquante."
        )

    return value.strip()


def _read_http_url(variable_name: str) -> str:
    """Retourne une URL HTTP ou HTTPS valide."""

    value = _read_required_string(variable_name)
    parsed_url = urlparse(value)

    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
    ):
        raise ConfigurationError(
            f"La variable {variable_name} doit contenir "
            "une URL HTTP valide."
        )

    return value.rstrip("/")


def _read_internal_api_key() -> str:
    """Retourne une clé interne suffisamment robuste."""

    internal_api_key = _read_required_string(
        "INTERNAL_API_KEY"
    )

    if internal_api_key in PLACEHOLDER_INTERNAL_API_KEYS:
        raise ConfigurationError(
            "INTERNAL_API_KEY utilise encore une valeur d'exemple."
        )

    if len(internal_api_key) < 32:
        raise ConfigurationError(
            "INTERNAL_API_KEY doit contenir "
            "au moins 32 caractères."
        )

    return internal_api_key


def _read_port(raw_port: str) -> int:
    """Convertit et valide le port du serveur MCP."""

    try:
        port = int(raw_port)

    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "MCP_PORT doit être un entier."
        ) from error

    if not 1 <= port <= 65535:
        raise ConfigurationError(
            "MCP_PORT doit être compris entre 1 et 65535."
        )

    return port
