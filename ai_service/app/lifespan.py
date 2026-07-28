"""Composition unique des ressources partagées du service IA."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import (
    AbstractAsyncContextManager,
    asynccontextmanager,
)

import httpx
from fastapi import FastAPI

from app.clients.mcp_client import ProductMCPClient
from app.clients.minimax_client import MiniMaxClient
from app.clients.ollama_client import OllamaClient
from app.config import Settings
from app.errors import MCPClientError
from app.services.answer_builder import AnswerBuilder
from app.services.answer_generator import AnswerGenerator
from app.services.context_resolver import ContextResolver
from app.services.conversation_store import ConversationStore
from app.services.intent_classifier import (
    CompletionClient,
    IntentClassifier,
)
from app.services.orchestrator import QueryOrchestrator


logger = logging.getLogger(__name__)

MCPClientFactory = Callable[..., ProductMCPClient]
MiniMaxClientFactory = Callable[..., MiniMaxClient]
OllamaHTTPClientFactory = Callable[[], httpx.AsyncClient]
Lifespan = Callable[
    [FastAPI],
    AbstractAsyncContextManager[None],
]


def provider_status(settings: Settings) -> str:
    """Décrit la configuration sans effectuer de requête fournisseur."""

    if settings.ai_model_provider in {"hybrid", "ollama"}:
        return "configured"

    if (
        settings.ai_model_provider == "nvidia"
        and settings.nvidia_api_key is not None
    ):
        return "configured"

    if (
        settings.ai_model_provider == "minimax"
        and settings.minimax_api_key is not None
    ):
        return "configured"

    if settings.ai_model_provider in {"nvidia", "minimax"}:
        return "fallback_rules"

    return "disabled"


def active_provider(settings: Settings) -> str:
    """Retourne le fournisseur réellement sélectionné au démarrage."""

    if (
        settings.ai_model_provider == "minimax"
        and settings.minimax_api_key is not None
    ):
        return "minimax"

    if (
        settings.ai_model_provider in {"hybrid", "nvidia"}
        and settings.nvidia_api_key is not None
    ):
        return "nvidia"

    if settings.ai_model_provider in {"hybrid", "ollama"}:
        return "ollama"

    return "rules"


def create_lifespan(
    settings: Settings,
    client_factory: MCPClientFactory,
    minimax_client_factory: MiniMaxClientFactory,
    ollama_http_client_factory: OllamaHTTPClientFactory,
) -> Lifespan:
    """Construit MCP, un fournisseur, un classifieur et un orchestrateur."""

    @asynccontextmanager
    async def lifespan(
        application: FastAPI,
    ) -> AsyncIterator[None]:
        """Ouvre les transports partagés et les ferme dans l'ordre inverse."""

        mcp_client = client_factory(
            server_url=str(settings.mcp_server_url),
            request_timeout_seconds=(
                settings.mcp_request_timeout_seconds
            ),
            max_concurrent_calls=settings.mcp_max_concurrent_calls,
            reconnect_attempts=settings.mcp_reconnect_attempts,
            reconnect_initial_delay_seconds=(
                settings.mcp_reconnect_initial_delay_seconds
            ),
            reconnect_max_delay_seconds=(
                settings.mcp_reconnect_max_delay_seconds
            ),
        )
        application.state.mcp_client = mcp_client
        minimax_client: MiniMaxClient | None = None
        ollama_http_client: httpx.AsyncClient | None = None
        orchestrator: QueryOrchestrator | None = None

        try:
            try:
                await mcp_client.connect()
            except MCPClientError:
                logger.warning(
                    "Le serveur MCP n'est pas disponible au démarrage."
                )

            (
                model_client,
                classification_max_tokens,
                answer_max_tokens,
                minimax_client,
                ollama_http_client,
            ) = _create_model_client(
                settings,
                minimax_client_factory,
                ollama_http_client_factory,
            )

            context_resolver = ContextResolver()
            classifier = IntentClassifier(
                model_client=model_client,
                max_tokens=classification_max_tokens,
                context_resolver=context_resolver,
            )
            answer_generator = (
                AnswerGenerator(
                    client=model_client,
                    max_tokens=answer_max_tokens,
                )
                if model_client is not None
                else None
            )
            conversation_store = ConversationStore(
                ttl_seconds=settings.conversation_ttl_seconds,
                max_turns=settings.conversation_max_turns,
                max_sessions=settings.conversation_max_sessions,
            )
            orchestrator = QueryOrchestrator(
                intent_classifier=classifier,
                client=mcp_client,
                answer_builder=AnswerBuilder(),
                answer_generator=answer_generator,
                conversation_store=conversation_store,
            )

            application.state.intent_classifier = classifier
            application.state.answer_generator = answer_generator
            application.state.conversation_store = conversation_store
            application.state.query_orchestrator = orchestrator
            application.state.ai_provider_status = provider_status(
                settings
            )
            application.state.active_ai_provider = active_provider(
                settings
            )

            yield
        finally:
            try:
                if orchestrator is not None:
                    await orchestrator.clear_conversations()
            finally:
                try:
                    if minimax_client is not None:
                        await minimax_client.aclose()
                finally:
                    try:
                        if ollama_http_client is not None:
                            await ollama_http_client.aclose()
                    finally:
                        try:
                            await mcp_client.close()
                        except MCPClientError:
                            logger.warning(
                                "La fermeture du client MCP a échoué."
                            )

    return lifespan


def _create_model_client(
    settings: Settings,
    minimax_client_factory: MiniMaxClientFactory,
    ollama_http_client_factory: OllamaHTTPClientFactory,
) -> tuple[
    CompletionClient | None,
    int,
    int,
    MiniMaxClient | None,
    httpx.AsyncClient | None,
]:
    """Sélectionne exactement un fournisseur, sans cascade par requête."""

    if (
        settings.ai_model_provider == "minimax"
        and settings.minimax_api_key is not None
    ):
        client = minimax_client_factory(
            api_key=settings.minimax_api_key.get_secret_value(),
            base_url=str(settings.minimax_base_url),
            model=settings.minimax_model,
            request_timeout_seconds=(
                settings.minimax_request_timeout_seconds
            ),
        )
        return (
            client,
            settings.minimax_classification_max_tokens,
            settings.minimax_answer_max_tokens,
            client,
            None,
        )

    if (
        settings.ai_model_provider in {"hybrid", "nvidia"}
        and settings.nvidia_api_key is not None
    ):
        client = minimax_client_factory(
            api_key=settings.nvidia_api_key.get_secret_value(),
            base_url=str(settings.nvidia_base_url),
            model=settings.nvidia_model,
            request_timeout_seconds=(
                settings.nvidia_request_timeout_seconds
            ),
            token_parameter="max_tokens",
            additional_payload={},
        )
        return (
            client,
            settings.nvidia_classification_max_tokens,
            settings.nvidia_answer_max_tokens,
            client,
            None,
        )

    if settings.ai_model_provider in {"hybrid", "ollama"}:
        http_client = ollama_http_client_factory()
        client = OllamaClient(
            http_client=http_client,
            base_url=str(settings.ollama_base_url),
            model=settings.ollama_model,
            request_timeout_seconds=(
                settings.ollama_request_timeout_seconds
            ),
        )
        return (
            client,
            settings.ollama_classification_max_tokens,
            settings.ollama_answer_max_tokens,
            None,
            http_client,
        )

    return (
        None,
        settings.minimax_classification_max_tokens,
        settings.minimax_answer_max_tokens,
        None,
        None,
    )
