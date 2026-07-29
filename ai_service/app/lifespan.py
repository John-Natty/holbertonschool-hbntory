"""Composition unique des ressources partagées du service IA."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import (
    AbstractAsyncContextManager,
    asynccontextmanager,
)

from fastapi import FastAPI

from app.clients.mcp_client import ProductMCPClient
from app.clients.nvidia_client import NVIDIAClient
from app.config import Settings
from app.errors import MCPClientError
from app.models.data import ProductListData
from app.services.answer_builder import AnswerBuilder
from app.services.answer_generator import AnswerGenerator
from app.services.catalog import CatalogSnapshot
from app.services.context_resolver import ContextResolver
from app.services.conversation_store import ConversationStore
from app.services.intent_classifier import (
    CompletionClient,
    IntentClassifier,
)
from app.services.orchestrator import QueryOrchestrator


logger = logging.getLogger(__name__)

MCPClientFactory = Callable[..., ProductMCPClient]
NVIDIAClientFactory = Callable[..., NVIDIAClient]
Lifespan = Callable[
    [FastAPI],
    AbstractAsyncContextManager[None],
]


def provider_status(settings: Settings) -> str:
    """Décrit la configuration sans effectuer de requête fournisseur."""

    if (
        settings.ai_model_provider == "nvidia"
        and settings.nvidia_api_key is not None
    ):
        return "configured"

    if settings.ai_model_provider == "nvidia":
        return "fallback_rules"

    return "disabled"


def active_provider(settings: Settings) -> str:
    """Retourne le fournisseur réellement sélectionné au démarrage."""

    if (
        settings.ai_model_provider == "nvidia"
        and settings.nvidia_api_key is not None
    ):
        return "nvidia"

    return "rules"


def create_lifespan(
    settings: Settings,
    client_factory: MCPClientFactory,
    nvidia_client_factory: NVIDIAClientFactory,
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
        nvidia_client: NVIDIAClient | None = None
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
                nvidia_client,
            ) = _create_model_client(
                settings,
                nvidia_client_factory,
            )

            context_resolver = ContextResolver()

            async def fetch_catalog_page(
                *,
                limit: int,
                offset: int,
            ) -> ProductListData:
                """Lit une page du catalogue au moment où elle est utile."""

                # La session MCP peut avoir été perdue depuis le
                # démarrage : on la rétablit comme le fait l'orchestrateur.
                await mcp_client.ensure_connected()

                return await mcp_client.list_products(
                    limit=limit,
                    offset=offset,
                )

            # Le classifieur n'a pas accès au serveur MCP : l'instantané
            # du catalogue lui sert d'intermédiaire pour relier un nom de
            # produit à son identifiant.
            catalog = CatalogSnapshot(fetch_catalog_page)
            classifier = IntentClassifier(
                model_client=model_client,
                max_tokens=classification_max_tokens,
                context_resolver=context_resolver,
                catalog=catalog,
            )
            answer_generator = (
                AnswerGenerator(
                    client=model_client,
                    max_tokens=answer_max_tokens,
                )
                if model_client is not None
                and settings.ai_natural_answers
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
                    if nvidia_client is not None:
                        await nvidia_client.aclose()
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
    nvidia_client_factory: NVIDIAClientFactory,
) -> tuple[
    CompletionClient | None,
    int,
    int,
    NVIDIAClient | None,
]:
    """Crée NVIDIA si sa clé existe, sinon le fallback reste local."""

    if (
        settings.ai_model_provider == "nvidia"
        and settings.nvidia_api_key is not None
    ):
        client = nvidia_client_factory(
            api_key=settings.nvidia_api_key.get_secret_value(),
            base_url=str(settings.nvidia_base_url),
            model=settings.nvidia_model,
            request_timeout_seconds=(
                settings.nvidia_request_timeout_seconds
            ),
        )
        return (
            client,
            settings.nvidia_classification_max_tokens,
            settings.nvidia_answer_max_tokens,
            client,
        )

    return (
        None,
        settings.nvidia_classification_max_tokens,
        settings.nvidia_answer_max_tokens,
        None,
    )
