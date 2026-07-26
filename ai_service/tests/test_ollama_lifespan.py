"""Tests du client Ollama partagé par le lifespan FastAPI."""

from collections.abc import Callable
import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.services.hybrid_intent_router import HybridIntentRouter
from app.services.ollama_classifier import OllamaIntentClassifier


pytestmark = pytest.mark.asyncio


class FakeLifecycleMCPClient:
    """Client MCP minimal pour tester uniquement le lifespan."""

    def __init__(self) -> None:
        """Prépare les compteurs et l'état prêt."""

        self._ready = False
        self.connect_count = 0
        self.close_count = 0

    @property
    def is_ready(self) -> bool:
        """Expose l'état utilisé par les routes."""

        return self._ready

    async def connect(self) -> None:
        """Simule une connexion MCP réussie."""

        self.connect_count += 1
        self._ready = True

    async def close(self) -> None:
        """Simule la fermeture MCP."""

        self.close_count += 1
        self._ready = False


class TrackingHTTPClientFactory:
    """Crée un unique client observable avec MockTransport."""

    def __init__(self) -> None:
        """Prépare les compteurs et la réponse unsupported."""

        self.factory_count = 0
        self.request_count = 0
        self.clients: list[httpx.AsyncClient] = []

    def __call__(self) -> httpx.AsyncClient:
        """Crée un client HTTP sans connexion réelle."""

        self.factory_count += 1

        def handler(_request: httpx.Request) -> httpx.Response:
            self.request_count += 1

            return httpx.Response(
                200,
                json={
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "type": "unsupported",
                                "reason": "Question inconnue.",
                            }
                        ),
                    },
                },
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        )
        self.clients.append(client)
        return client


def ollama_settings() -> Settings:
    """Active le fournisseur Ollama dans une configuration locale."""

    return Settings(
        mcp_server_url="http://mcp.test/mcp",
        ai_intent_provider="ollama",
        ollama_base_url="http://ollama.test:11434",
        ollama_model="gemma3:latest",
        ollama_request_timeout_seconds=2,
    )


def mcp_factory(
    client: FakeLifecycleMCPClient,
) -> Callable[..., FakeLifecycleMCPClient]:
    """Retourne une fabrique MCP compatible avec create_app."""

    def factory(
        **_configuration: object,
    ) -> FakeLifecycleMCPClient:
        return client

    return factory


async def test_ollama_client_is_created_once_without_startup_call() -> None:
    """Construit le routeur hybride sans contacter Ollama."""

    mcp_client = FakeLifecycleMCPClient()
    http_factory = TrackingHTTPClientFactory()
    application = create_app(
        settings=ollama_settings(),
        mcp_client_factory=mcp_factory(mcp_client),
        ollama_http_client_factory=http_factory,
    )

    async with application.router.lifespan_context(application):
        assert isinstance(
            application.state.intent_classifier,
            OllamaIntentClassifier,
        )
        assert isinstance(
            application.state.intent_router,
            HybridIntentRouter,
        )
        assert http_factory.factory_count == 1
        assert http_factory.request_count == 0
        assert http_factory.clients[0].is_closed is False

    assert http_factory.clients[0].is_closed is True
    assert mcp_client.close_count == 1


async def test_two_queries_share_one_http_client() -> None:
    """Réutilise le même client pour deux classifications nécessaires."""

    mcp_client = FakeLifecycleMCPClient()
    http_factory = TrackingHTTPClientFactory()
    application = create_app(
        settings=ollama_settings(),
        mcp_client_factory=mcp_factory(mcp_client),
        ollama_http_client_factory=http_factory,
    )
    transport = ASGITransport(app=application)

    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            first_response = await client.post(
                "/query",
                json={
                    "question": "question naturelle inconnue",
                },
            )
            second_response = await client.post(
                "/query",
                json={
                    "question": "autre formulation inconnue",
                },
            )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["type"] == "text"
    assert second_response.json()["type"] == "text"
    assert http_factory.factory_count == 1
    assert http_factory.request_count == 2
    assert http_factory.clients[0].is_closed is True


async def test_readiness_does_not_depend_on_ollama() -> None:
    """Laisse health et ready fonctionner sans appel au fournisseur."""

    mcp_client = FakeLifecycleMCPClient()
    http_factory = TrackingHTTPClientFactory()
    application = create_app(
        settings=ollama_settings(),
        mcp_client_factory=mcp_factory(mcp_client),
        ollama_http_client_factory=http_factory,
    )
    transport = ASGITransport(app=application)

    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            health_response = await client.get("/health")
            ready_response = await client.get("/ready")

    assert health_response.status_code == 200
    assert ready_response.status_code == 200
    assert ready_response.json()["mcp"] == "connected"
    assert http_factory.request_count == 0


async def test_rules_mode_never_creates_ollama_client() -> None:
    """N'appelle pas la fabrique HTTP lorsque le mode rules est actif."""

    mcp_client = FakeLifecycleMCPClient()
    http_factory = TrackingHTTPClientFactory()
    settings = ollama_settings().model_copy(
        update={
            "ai_intent_provider": "rules",
        }
    )
    application = create_app(
        settings=settings,
        mcp_client_factory=mcp_factory(mcp_client),
        ollama_http_client_factory=http_factory,
    )

    async with application.router.lifespan_context(application):
        assert application.state.intent_classifier is None

    assert http_factory.factory_count == 0
    assert http_factory.clients == []
