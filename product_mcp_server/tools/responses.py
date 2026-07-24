#!/usr/bin/env python3
"""Construction des réponses structurées retournées par les outils MCP."""

from typing import Any

from clients.errors import (
    ExternalServiceResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    InvalidClientParameterError,
    MCPClientError,
    ResourceNotFoundError,
)


def success_response(**data: Any) -> dict[str, Any]:
    """Construit une réponse MCP réussie et structurée."""

    return {
        "success": True,
        **data,
        "error": None,
    }


def error_response(error: MCPClientError) -> dict[str, Any]:
    """Transforme une erreur client connue en réponse MCP structurée."""

    error_code = _error_code(error)

    return {
        "success": False,
        "error": {
            "code": error_code,
            "message": str(error),
        },
    }


def _error_code(error: MCPClientError) -> str:
    """Retourne le code public correspondant à une erreur client."""

    if isinstance(error, InvalidClientParameterError):
        return "invalid_parameters"

    if isinstance(error, ResourceNotFoundError):
        return "resource_not_found"

    if isinstance(error, ExternalServiceTimeoutError):
        return "service_timeout"

    if isinstance(error, ExternalServiceUnavailableError):
        return "service_unavailable"

    if isinstance(error, ExternalServiceResponseError):
        return "invalid_service_response"

    return "client_error"
