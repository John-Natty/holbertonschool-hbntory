"""Dépendances injectables des routes du service IA."""

from typing import cast

from fastapi import Request

from app.clients.mcp_client import ProductMCPClient
from app.services.query_service import (
    QueryService,
    UnavailableQueryService,
)


_query_service = UnavailableQueryService()


async def get_query_service() -> QueryService:
    """Retourne le service de requête utilisé par l'API."""

    return _query_service


async def get_mcp_client(
    request: Request,
) -> ProductMCPClient | None:
    """Lit le client partagé sans initier de reconnexion."""

    client = getattr(
        request.app.state,
        "mcp_client",
        None,
    )

    if client is None:
        return None

    return cast(ProductMCPClient, client)
