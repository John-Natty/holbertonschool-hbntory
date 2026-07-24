"""Tests du lifespan FastAPI et de la disponibilité MCP."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.errors import MCPConnectionError
from app.main import create_app


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
        self.close_count = 0

    @property
    def is_ready(self) -> bool:
        """Expose l'état observé par GET /ready."""

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


def create_test_settings() -> Settings:
    """Retourne une configuration entièrement locale."""

    return Settings(
        mcp_server_url="http://mcp.test/mcp",
        mcp_request_timeout_seconds=3.5,
        mcp_max_concurrent_calls=4,
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
        assert lifecycle_client.connect_count == 1
        assert lifecycle_client.close_count == 0
        assert factory.calls == [
            {
                "server_url": "http://mcp.test/mcp",
                "request_timeout_seconds": 3.5,
                "max_concurrent_calls": 4,
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
    }
    assert lifecycle_client.connect_count == 1
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
    }
    assert second_ready_response.status_code == 503
    assert lifecycle_client.connect_count == 1
    assert lifecycle_client.close_count == 1


async def test_query_remains_disconnected_from_mcp_orchestration() -> None:
    """Conserve UnavailableQueryService malgré un client MCP prêt."""

    lifecycle_client = FakeLifecycleClient()
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
                "/query",
                json={
                    "question": "Où trouver le produit 12 ?",
                },
            )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert lifecycle_client.connect_count == 1


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
