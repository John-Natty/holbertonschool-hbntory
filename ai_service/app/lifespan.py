"""Cycle de vie du client MCP partagé par FastAPI."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import (
    AbstractAsyncContextManager,
    asynccontextmanager,
)

import httpx
from fastapi import FastAPI

from app.clients.mcp_client import ProductMCPClient
from app.config import Settings
from app.errors import MCPClientError
from app.services.answer_builder import AnswerBuilder
from app.services.hybrid_intent_router import HybridIntentRouter
from app.services.intent_anchor import IntentAnchorValidator
from app.services.intent_classifier import IntentClassifier
from app.services.intent_router import (
    IntentRouter,
    RuleBasedIntentRouter,
)
from app.services.ollama_classifier import OllamaIntentClassifier
from app.services.orchestrator import QueryOrchestrator
from app.services.query_service import MCPQueryService


logger = logging.getLogger(__name__)

MCPClientFactory = Callable[..., ProductMCPClient]
OllamaHTTPClientFactory = Callable[[], httpx.AsyncClient]
Lifespan = Callable[
    [FastAPI],
    AbstractAsyncContextManager[None],
]


def create_lifespan(
    settings: Settings,
    client_factory: MCPClientFactory,
    ollama_http_client_factory: OllamaHTTPClientFactory,
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
        ollama_http_client: httpx.AsyncClient | None = None

        try:
            try:
                await client.connect()
            except MCPClientError:
                logger.warning(
                    "Le serveur MCP n'est pas disponible au démarrage."
                )

            rule_router = RuleBasedIntentRouter()
            intent_classifier: IntentClassifier | None = None
            intent_router: IntentRouter

            if settings.ai_intent_provider == "ollama":
                ollama_http_client = (
                    ollama_http_client_factory()
                )
                intent_classifier = OllamaIntentClassifier(
                    http_client=ollama_http_client,
                    base_url=str(settings.ollama_base_url),
                    model=settings.ollama_model,
                    request_timeout_seconds=(
                        settings.ollama_request_timeout_seconds
                    ),
                )
                intent_router = HybridIntentRouter(
                    rule_router=rule_router,
                    classifier=intent_classifier,
                    anchor_validator=IntentAnchorValidator(),
                )
            else:
                intent_router = rule_router

            application.state.intent_classifier = intent_classifier
            application.state.intent_router = intent_router

            orchestrator = QueryOrchestrator(
                intent_router=intent_router,
                client=client,
                answer_builder=AnswerBuilder(),
            )
            application.state.query_service = MCPQueryService(
                orchestrator
            )

            yield
        finally:
            try:
                if ollama_http_client is not None:
                    await ollama_http_client.aclose()
            finally:
                try:
                    await client.close()
                except MCPClientError:
                    logger.warning(
                        "La fermeture du client MCP a échoué."
                    )

    return lifespan
