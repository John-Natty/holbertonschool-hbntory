"""Dépendances injectables des routes du service IA."""

from typing import cast

from fastapi import Request

from app.clients.mcp_client import ProductMCPClient
from app.services.orchestrator import QueryOrchestrator


async def get_query_orchestrator(
    request: Request,
) -> QueryOrchestrator | None:
    """Lit l'unique orchestrateur construit pendant le lifespan."""

    orchestrator = getattr(
        request.app.state,
        "query_orchestrator",
        None,
    )

    if orchestrator is None:
        return None

    return cast(QueryOrchestrator, orchestrator)


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
