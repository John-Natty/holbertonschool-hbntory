"""Cycle de vie du client MCP partagé par FastAPI."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import (
    AbstractAsyncContextManager,
    asynccontextmanager,
)

from fastapi import FastAPI

from app.clients.mcp_client import ProductMCPClient
from app.config import Settings
from app.errors import MCPClientError
from app.services.answer_builder import AnswerBuilder
from app.services.intent_router import RuleBasedIntentRouter
from app.services.orchestrator import QueryOrchestrator
from app.services.query_service import MCPQueryService


logger = logging.getLogger(__name__)

MCPClientFactory = Callable[..., ProductMCPClient]
Lifespan = Callable[
    [FastAPI],
    AbstractAsyncContextManager[None],
]


def create_lifespan(
    settings: Settings,
    client_factory: MCPClientFactory,
) -> Lifespan:
    """Construit un lifespan injectable et sans effet à l'import."""

    @asynccontextmanager
    async def lifespan(
        application: FastAPI,
    ) -> AsyncIterator[None]:
        """Connecte une fois le client puis le ferme à l'arrêt."""

        client = client_factory(
            server_url=str(settings.mcp_server_url),
            request_timeout_seconds=(
                settings.mcp_request_timeout_seconds
            ),
            max_concurrent_calls=settings.mcp_max_concurrent_calls,
        )
        application.state.mcp_client = client

        try:
            try:
                await client.connect()
            except MCPClientError:
                logger.warning(
                    "Le serveur MCP n'est pas disponible au démarrage."
                )

            orchestrator = QueryOrchestrator(
                intent_router=RuleBasedIntentRouter(),
                client=client,
                answer_builder=AnswerBuilder(),
            )
            application.state.query_service = MCPQueryService(
                orchestrator
            )

            yield
        finally:
            try:
                await client.close()
            except MCPClientError:
                logger.warning(
                    "La fermeture du client MCP a échoué."
                )

    return lifespan
