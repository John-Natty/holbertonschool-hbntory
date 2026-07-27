"""Dépendances injectables des routes du service IA."""

from typing import cast

from fastapi import Request

from app.clients.mcp_client import ProductMCPClient
from app.services.query_service import (
    QueryService,
    UnavailableQueryService,
)


_query_service = UnavailableQueryService()


async def get_query_service(
    request: Request,
) -> QueryService:
    """Lit le service partagé, avec un fallback contrôlé."""

    service = getattr(
        request.app.state,
        "query_service",
        None,
    )

    if service is None:
        return _query_service

    return cast(QueryService, service)


async def get_mcp_client(
    request: Request,
) -> ProductMCPClient | None:
    """Lit le client partagé utilisé par la disponibilité."""

    client = getattr(
        request.app.state,
        "mcp_client",
        None,
    )

    if client is None:
        return None

    return cast(ProductMCPClient, client)
