#!/usr/bin/env python3
"""Erreurs communes aux clients HTTP du serveur MCP."""


class MCPClientError(RuntimeError):
    """Erreur de base produite par un client HTTP du serveur MCP."""


class InvalidClientParameterError(MCPClientError):
    """Erreur levée lorsqu'un paramètre fourni au client est invalide."""


class ExternalServiceUnavailableError(MCPClientError):
    """Erreur levée lorsqu'un service HTTP est injoignable."""


class ExternalServiceTimeoutError(MCPClientError):
    """Erreur levée lorsqu'un service HTTP répond trop lentement."""


class ExternalServiceResponseError(MCPClientError):
    """Erreur levée lorsqu'un service retourne une réponse incorrecte."""


class ResourceNotFoundError(MCPClientError):
    """Erreur levée lorsqu'une ressource demandée n'existe pas."""
