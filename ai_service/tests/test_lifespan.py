"""Tests du lifespan FastAPI et de la disponibilité MCP."""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.errors import MCPConnectionError
from app.main import create_app
from app.services.conversation_store import ConversationStore
from app.services.intent_classifier import IntentClassifier
from app.services.orchestrator import QueryOrchestrator


pytestmark = pytest.mark.asyncio


class FakeLifecycleClient:
    """Double minimal injecté uniquement autour du lifespan."""

    def __init__(
        self,
        *,
        ready_after_connect: bool = True,
        connect_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        """Configure l'état et les erreurs du double."""

        self._ready = False
        self.ready_after_connect = ready_after_connect
        self.connect_error = connect_error
        self.close_error = close_error
        self.connect_count = 0
        self.ensure_count = 0
        self.close_count = 0

    @property
    def is_ready(self) -> bool:
        """Expose l'état observé par GET /ready."""

        return self._ready

    async def ensure_connected(self) -> bool:
        """Simule une reconnexion unique lorsque le client est indisponible."""

        self.ensure_count += 1

        if self._ready:
            return True

        try:
            await self.connect()
        except MCPConnectionError:
            return False

        return self._ready

    async def connect(self) -> None:
        """Simule la connexion du client."""

        self.connect_count += 1

        if self.connect_error is not None:
            raise self.connect_error

        self._ready = self.ready_after_connect

    async def close(self) -> None:
        """Simule la fermeture du client."""

        self.close_count += 1
        self._ready = False

        if self.close_error is not None:
            raise self.close_error


class FakeClientFactory:
    """Enregistre la construction unique et sa configuration."""

    def __init__(self, client: FakeLifecycleClient) -> None:
        """Conserve le client qui sera retourné."""

        self.client = client
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        **configuration: object,
    ) -> FakeLifecycleClient:
        """Retourne le client configuré pour le test."""

        self.calls.append(configuration)
        return self.client


class FakeModelClient:
    """Double du transport de complétion partagé."""

    def __init__(self) -> None:
        self.close_count = 0

    async def complete(self, messages, *, max_tokens: int) -> str:
        """N'est pas appelé par les tests de composition."""

        raise AssertionError("Complétion inattendue.")

    async def aclose(self) -> None:
        """Compte la fermeture du client partagé."""

        self.close_count += 1


class FakeModelFactory:
    """Observe le fournisseur distant construit par le lifespan."""

    def __init__(self, client: FakeModelClient) -> None:
        self.client = client
        self.calls: list[dict[str, object]] = []

    def __call__(self, **configuration: object) -> FakeModelClient:
        self.calls.append(configuration)
        return self.client


class TrackingHTTPClientFactory:
    """Crée un client Ollama local et observable sans réseau."""

    def __init__(self) -> None:
        self.clients: list[httpx.AsyncClient] = []

    def __call__(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(500)
            )
        )
        self.clients.append(client)
        return client


def create_test_settings() -> Settings:
    """Retourne une configuration entièrement locale."""

    return Settings(
        mcp_server_url="http://mcp.test/mcp",
        mcp_request_timeout_seconds=3.5,
        mcp_max_concurrent_calls=4,
        ai_model_provider="rules",
    )


async def request_in_lifespan(
    application: FastAPI,
    path: str,
) -> tuple[int, dict[str, object]]:
    """Effectue une requête ASGI avec le lifespan actif."""

    transport = ASGITransport(app=application)

    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(path)

    return response.status_code, response.json()


async def test_lifespan_builds_connects_and_closes_once() -> None:
    """Partage un client construit, connecté et fermé une seule fois."""

    lifecycle_client = FakeLifecycleClient()
    factory = FakeClientFactory(lifecycle_client)
    application = create_app(
        settings=create_test_settings(),
        mcp_client_factory=factory,
    )

    async with application.router.lifespan_context(application):
        assert application.state.mcp_client is lifecycle_client
        assert isinstance(
            application.state.query_orchestrator,
            QueryOrchestrator,
        )
        assert isinstance(
            application.state.intent_classifier,
            IntentClassifier,
        )
        assert application.state.answer_generator is None
        assert isinstance(
            application.state.conversation_store,
            ConversationStore,
        )
        assert lifecycle_client.connect_count == 1
        assert lifecycle_client.close_count == 0
        assert factory.calls == [
            {
                "server_url": "http://mcp.test/mcp",
                "request_timeout_seconds": 3.5,
                "max_concurrent_calls": 4,
                "reconnect_attempts": 3,
                "reconnect_initial_delay_seconds": 0.25,
                "reconnect_max_delay_seconds": 2.0,
            }
        ]

    assert lifecycle_client.close_count == 1


async def test_ready_returns_200_when_mcp_is_connected() -> None:
    """Expose une réponse prête lorsque la connexion a réussi."""

    lifecycle_client = FakeLifecycleClient()
    application = create_app(
        settings=create_test_settings(),
        mcp_client_factory=FakeClientFactory(lifecycle_client),
    )

    status_code, body = await request_in_lifespan(
        application,
        "/ready",
    )

    assert status_code == 200
    assert body == {
        "status": "ready",
        "service": "ai-service",
        "mcp": "connected",
        "provider": "rules",
        "provider_status": "disabled",
        "active_provider": "rules",
    }
    assert lifecycle_client.connect_count == 1
    assert lifecycle_client.ensure_count == 1
    assert lifecycle_client.close_count == 1


async def test_expected_connection_failure_keeps_http_available() -> None:
    """Garde health à 200 et ready à 503 sans nouvelle connexion."""

    lifecycle_client = FakeLifecycleClient(
        connect_error=MCPConnectionError(
            "Connexion indisponible."
        )
    )
    application = create_app(
        settings=create_test_settings(),
        mcp_client_factory=FakeClientFactory(lifecycle_client),
    )
    transport = ASGITransport(app=application)

    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            health_response = await client.get("/health")
            ready_response = await client.get("/ready")
            second_ready_response = await client.get("/ready")

    assert health_response.status_code == 200
    assert ready_response.status_code == 503
    assert ready_response.json() == {
        "status": "not_ready",
        "service": "ai-service",
        "mcp": "disconnected",
        "provider": "rules",
        "provider_status": "disabled",
        "active_provider": "rules",
    }
    assert second_ready_response.status_code == 503
    assert lifecycle_client.connect_count == 3
    assert lifecycle_client.ensure_count == 2
    assert lifecycle_client.close_count == 1


async def test_real_streamable_transport_failure_keeps_http_available(
) -> None:
    """Reproduit une connexion locale refusée avec le transport officiel."""

    application = create_app(
        settings=Settings(
            mcp_server_url="http://127.0.0.1:9/mcp",
            mcp_request_timeout_seconds=0.2,
            mcp_reconnect_attempts=1,
            mcp_reconnect_initial_delay_seconds=0,
            mcp_reconnect_max_delay_seconds=0,
            ai_model_provider="rules",
        )
    )
    transport = ASGITransport(app=application)

    async with asyncio.timeout(5):
        async with application.router.lifespan_context(
            application
        ):
            async with AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                health_response = await client.get("/health")
                ready_response = await client.get("/ready")
                query_response = await client.post(
                    "/api/query",
                    json={
                        "question": "liste les produits",
                    },
                )

    assert health_response.status_code == 200
    assert ready_response.status_code == 503
    assert query_response.status_code == 503
    assert query_response.json()["error"] == {
        "code": "service_unavailable",
        "message": "Le serveur MCP n’est pas connecté.",
    }


async def test_ready_recovers_after_connection_is_restored() -> None:
    """Déclenche une nouvelle connexion bornée depuis GET /ready."""

    lifecycle_client = FakeLifecycleClient(
        connect_error=MCPConnectionError(
            "Connexion indisponible."
        )
    )
    application = create_app(
        settings=create_test_settings(),
        mcp_client_factory=FakeClientFactory(lifecycle_client),
    )
    transport = ASGITransport(app=application)

    async with application.router.lifespan_context(application):
        lifecycle_client.connect_error = None

        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["mcp"] == "connected"
    assert lifecycle_client.connect_count == 2
    assert lifecycle_client.ensure_count == 1


async def test_query_returns_503_when_shared_client_is_not_ready() -> None:
    """Retourne une indisponibilité avant tout appel MCP."""

    lifecycle_client = FakeLifecycleClient(
        ready_after_connect=False
    )
    application = create_app(
        settings=create_test_settings(),
        mcp_client_factory=FakeClientFactory(lifecycle_client),
    )
    transport = ASGITransport(app=application)

    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/query",
                json={
                    "question": "Où trouver le produit 12 ?",
                },
            )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert lifecycle_client.connect_count == 2
    assert lifecycle_client.ensure_count == 1


async def test_missing_lifespan_state_returns_controlled_503(
    client: AsyncClient,
) -> None:
    """Contrôle l'absence du client lorsque le lifespan n'est pas lancé."""

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "ai-service",
        "mcp": "disconnected",
        "provider": "hybrid",
        "provider_status": "configured",
        "active_provider": "ollama",
    }


async def test_unexpected_startup_error_is_not_masked() -> None:
    """Laisse remonter une erreur Python inattendue au démarrage."""

    lifecycle_client = FakeLifecycleClient(
        connect_error=RuntimeError("bug de démarrage")
    )
    application = create_app(
        settings=create_test_settings(),
        mcp_client_factory=FakeClientFactory(lifecycle_client),
    )

    with pytest.raises(RuntimeError, match="bug de démarrage"):
        async with application.router.lifespan_context(application):
            pass

    assert lifecycle_client.close_count == 1


async def test_unexpected_shutdown_error_is_not_masked() -> None:
    """Laisse remonter une erreur Python inattendue à l'arrêt."""

    lifecycle_client = FakeLifecycleClient(
        close_error=RuntimeError("bug de fermeture")
    )
    application = create_app(
        settings=create_test_settings(),
        mcp_client_factory=FakeClientFactory(lifecycle_client),
    )

    with pytest.raises(RuntimeError, match="bug de fermeture"):
        async with application.router.lifespan_context(application):
            pass


async def test_expected_shutdown_error_is_controlled() -> None:
    """Contrôle une erreur MCP attendue pendant la fermeture."""

    lifecycle_client = FakeLifecycleClient(
        close_error=MCPConnectionError(
            "Fermeture indisponible."
        )
    )
    application = create_app(
        settings=create_test_settings(),
        mcp_client_factory=FakeClientFactory(lifecycle_client),
    )

    async with application.router.lifespan_context(application):
        assert lifecycle_client.is_ready is True

    assert lifecycle_client.close_count == 1


@pytest.mark.parametrize(
    ("provider", "key_field", "expected_active"),
    [
        ("minimax", "minimax_api_key", "minimax"),
        ("nvidia", "nvidia_api_key", "nvidia"),
        ("hybrid", "nvidia_api_key", "nvidia"),
    ],
)
async def test_lifespan_selects_one_remote_client_and_closes_it(
    provider: str,
    key_field: str,
    expected_active: str,
) -> None:
    """Partage un seul client entre compréhension et rédaction."""

    model_client = FakeModelClient()
    model_factory = FakeModelFactory(model_client)
    settings_data: dict[str, object] = {
        "ai_model_provider": provider,
        key_field: "provider-secret-for-test",
    }
    application = create_app(
        settings=Settings(**settings_data),
        mcp_client_factory=FakeClientFactory(
            FakeLifecycleClient()
        ),
        minimax_client_factory=model_factory,
    )

    async with application.router.lifespan_context(application):
        classifier = application.state.intent_classifier
        generator = application.state.answer_generator

        assert application.state.active_ai_provider == expected_active
        assert classifier._model_client is model_client
        assert generator._client is model_client
        assert len(model_factory.calls) == 1
        assert model_client.close_count == 0

    assert model_client.close_count == 1

    configuration = model_factory.calls[0]
    if expected_active == "nvidia":
        assert configuration["token_parameter"] == "max_tokens"
        assert configuration["additional_payload"] == {}
        assert configuration["model"] == "minimaxai/minimax-m3"
    else:
        assert "token_parameter" not in configuration
        assert "additional_payload" not in configuration
        assert configuration["model"] == "MiniMax-M3"


@pytest.mark.parametrize("provider", ["nvidia", "minimax"])
async def test_missing_remote_key_selects_rules_fallback(
    provider: str,
) -> None:
    """N'invente pas de clé et ne construit aucun client distant."""

    model_client = FakeModelClient()
    model_factory = FakeModelFactory(model_client)
    application = create_app(
        settings=Settings(ai_model_provider=provider),
        mcp_client_factory=FakeClientFactory(
            FakeLifecycleClient()
        ),
        minimax_client_factory=model_factory,
    )

    async with application.router.lifespan_context(application):
        assert application.state.active_ai_provider == "rules"
        assert application.state.answer_generator is None
        assert application.state.ai_provider_status == "fallback_rules"

    assert model_factory.calls == []
    assert model_client.close_count == 0


@pytest.mark.parametrize("provider", ["ollama", "hybrid"])
async def test_ollama_selection_shares_and_closes_http_client(
    provider: str,
) -> None:
    """Construit un seul transport local lorsqu'aucune clé NVIDIA existe."""

    http_factory = TrackingHTTPClientFactory()
    application = create_app(
        settings=Settings(ai_model_provider=provider),
        mcp_client_factory=FakeClientFactory(
            FakeLifecycleClient()
        ),
        ollama_http_client_factory=http_factory,
    )

    async with application.router.lifespan_context(application):
        assert application.state.active_ai_provider == "ollama"
        assert application.state.answer_generator is not None
        assert len(http_factory.clients) == 1
        assert http_factory.clients[0].is_closed is False

    assert http_factory.clients[0].is_closed is True
