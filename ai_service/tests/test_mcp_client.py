"""Tests unitaires du véritable client MCP, sans réseau."""

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from app.clients.mcp_client import (
    EXPECTED_TOOLS,
    ProductMCPClient,
)
from app.errors import (
    MCPConnectionError,
    MCPInvalidArgumentError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPToolNotFoundError,
    MCPToolResponseError,
)
from app.models.data import (
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
)
from app.models.mcp import ShoppingListItem


pytestmark = pytest.mark.asyncio

PRODUCT = {
    "id": 12,
    "sku": "HB-TEST-0012",
    "name": "Produit de test",
    "description": "Description.",
    "category": "Tests",
    "brand": "HBntory",
    "supplier_id": "SUP-001",
    "supplier_name": "Fournisseur",
    "unit_price": 49.99,
    "currency": "EUR",
    "discontinued": False,
    "weight_kg": 1.25,
    "tags": ["test"],
    "updated_at": "2026-07-24T12:00:00Z",
    "supplier": None,
}

SUCCESS_RESULTS = {
    "list_products": {
        "success": True,
        "count": 1,
        "limit": 20,
        "offset": 0,
        "products": [PRODUCT],
        "error": None,
    },
    "get_product_details": {
        "success": True,
        "product": PRODUCT,
        "error": None,
    },
    "get_stock_by_product": {
        "success": True,
        "product_id": 12,
        "branches": [
            {
                "branch_id": 1,
                "branch_name": "Toulouse",
                "quantity": 8,
            },
        ],
        "error": None,
    },
    "get_stock_by_branch": {
        "success": True,
        "branch": {
            "id": 1,
            "name": "Toulouse",
        },
        "stocks": [
            {
                "product_id": 12,
                "product_name": "Produit de test",
                "unit_price": 49.99,
                "currency": "EUR",
                "quantity": 8,
            },
        ],
        "error": None,
    },
    "check_shopping_list": {
        "success": True,
        "matching_branches": [
            {
                "branch_id": 1,
                "branch_name": "Toulouse",
                "items": [
                    {
                        "product_id": 12,
                        "requested_quantity": 2,
                        "available_quantity": 8,
                    },
                ],
            },
        ],
        "error": None,
    },
}


def tool_call_result(
    result: object,
    *,
    is_error: object = False,
) -> SimpleNamespace:
    """Construit une réponse semblable à CallToolResult."""

    return SimpleNamespace(
        isError=is_error,
        structuredContent={
            "result": result,
        },
    )


class FakeTransportContext:
    """Simule le contexte du transport Streamable HTTP."""

    def __init__(self) -> None:
        """Prépare les compteurs du contexte."""

        self.enter_count = 0
        self.exit_count = 0

    async def __aenter__(
        self,
    ) -> tuple[str, str, Any]:
        """Retourne deux flux opaques et un lecteur de session."""

        self.enter_count += 1
        return "read-stream", "write-stream", lambda: "session-id"

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Enregistre la fermeture du transport."""

        self.exit_count += 1


class FakeSession:
    """Simule uniquement l'interface officielle ClientSession."""

    def __init__(
        self,
        tools: object,
    ) -> None:
        """Prépare les réponses et compteurs observables."""

        self.tools = tools
        self.enter_count = 0
        self.exit_count = 0
        self.initialize_count = 0
        self.list_tools_count = 0
        self.ping_count = 0
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.call_handler = None
        self.initialize_error = None
        self.ping_error = None
        self.next_cursor = None

    async def __aenter__(self) -> "FakeSession":
        """Ouvre la fausse session."""

        self.enter_count += 1
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Ferme la fausse session."""

        self.exit_count += 1

    async def initialize(self) -> None:
        """Enregistre l'initialisation MCP."""

        self.initialize_count += 1

        if self.initialize_error is not None:
            raise self.initialize_error

    async def list_tools(self) -> SimpleNamespace:
        """Retourne la liste configurable des outils."""

        self.list_tools_count += 1
        return SimpleNamespace(
            tools=self.tools,
            nextCursor=self.next_cursor,
        )

    async def send_ping(self) -> None:
        """Vérifie la génération de session sans appel métier."""

        self.ping_count += 1

        if self.ping_error is not None:
            raise self.ping_error

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        **_kwargs: object,
    ) -> SimpleNamespace:
        """Retourne la réponse configurée pour un outil."""

        self.calls.append((name, arguments))

        if self.call_handler is not None:
            return await self.call_handler(name, arguments)

        return tool_call_result(SUCCESS_RESULTS[name])


class FakeMCPEnvironment:
    """Injecte le transport et la session dans ProductMCPClient."""

    def __init__(
        self,
        tool_names: object | None = None,
    ) -> None:
        """Crée un environnement MCP entièrement en mémoire."""

        if tool_names is None:
            tool_names = sorted(EXPECTED_TOOLS)

        if isinstance(tool_names, list):
            tools: object = [
                SimpleNamespace(name=name)
                for name in tool_names
            ]
        else:
            tools = tool_names

        self.transport = FakeTransportContext()
        self.session = FakeSession(tools)
        self.transport_factory_count = 0
        self.session_factory_count = 0
        self.transport_url = None
        self.session_arguments = None

    def transport_factory(
        self,
        url: str,
    ) -> FakeTransportContext:
        """Retourne toujours le même transport observable."""

        self.transport_factory_count += 1
        self.transport_url = url
        return self.transport

    def session_factory(
        self,
        *arguments: object,
        **keywords: object,
    ) -> FakeSession:
        """Retourne toujours la même session observable."""

        self.session_factory_count += 1
        self.session_arguments = (arguments, keywords)
        return self.session

    def create_client(
        self,
        *,
        timeout: float = 1.0,
        concurrency: int = 10,
        reconnect_attempts: int = 3,
        reconnect_initial_delay: float = 0.25,
        reconnect_max_delay: float = 2.0,
    ) -> ProductMCPClient:
        """Crée le vrai client avec les deux fabriques injectées."""

        return ProductMCPClient(
            "http://mcp.test/mcp",
            request_timeout_seconds=timeout,
            max_concurrent_calls=concurrency,
            reconnect_attempts=reconnect_attempts,
            reconnect_initial_delay_seconds=(
                reconnect_initial_delay
            ),
            reconnect_max_delay_seconds=reconnect_max_delay,
            transport_factory=self.transport_factory,
            session_factory=self.session_factory,
        )


class SequencedMCPEnvironment:
    """Crée une nouvelle paire transport-session à chaque connexion."""

    def __init__(
        self,
        *,
        failures: int = 0,
    ) -> None:
        """Configure le nombre d'initialisations réseau en échec."""

        self.failures_remaining = failures
        self.transports: list[FakeTransportContext] = []
        self.sessions: list[FakeSession] = []

    def transport_factory(
        self,
        _url: str,
    ) -> FakeTransportContext:
        """Crée un transport propre pour la nouvelle génération."""

        transport = FakeTransportContext()
        self.transports.append(transport)
        return transport

    def session_factory(
        self,
        *_arguments: object,
        **_keywords: object,
    ) -> FakeSession:
        """Crée une session réussie ou une connexion refusée."""

        session = FakeSession(
            [
                SimpleNamespace(name=name)
                for name in sorted(EXPECTED_TOOLS)
            ]
        )

        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            session.initialize_error = httpx.ConnectError(
                "Connexion locale refusée."
            )

        self.sessions.append(session)
        return session

    def create_client(
        self,
        *,
        attempts: int = 3,
        initial_delay: float = 0,
        max_delay: float = 0,
    ) -> ProductMCPClient:
        """Crée le client réel avec des générations observables."""

        return ProductMCPClient(
            "http://mcp.test/mcp",
            request_timeout_seconds=1,
            max_concurrent_calls=10,
            reconnect_attempts=attempts,
            reconnect_initial_delay_seconds=initial_delay,
            reconnect_max_delay_seconds=max_delay,
            transport_factory=self.transport_factory,
            session_factory=self.session_factory,
        )


async def test_connect_initializes_and_validates_tools() -> None:
    """Initialise une session et vérifie exactement cinq outils."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    await client.connect()

    assert client.is_ready is True
    assert environment.transport_url == "http://mcp.test/mcp"
    assert environment.session.initialize_count == 1
    assert environment.session.list_tools_count == 1
    assert environment.transport.enter_count == 1
    assert environment.session.enter_count == 1

    await client.close()


async def test_connection_check_updates_runtime_readiness(
) -> None:
    """Invalide la disponibilité lorsque la session MCP disparaît."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()
    await client.connect()

    assert await client.check_connection() is True
    assert environment.session.ping_count == 1
    assert client.is_ready is True

    environment.session.ping_error = httpx.ConnectError(
        "Session MCP perdue."
    )

    assert await client.check_connection() is False
    assert client.is_ready is False

    await client.close()


async def test_internal_initialization_cancellation_is_connection_error(
) -> None:
    """Traduit l'annulation interne du SDK sans conserver de ressource."""

    environment = FakeMCPEnvironment()
    environment.session.initialize_error = asyncio.CancelledError()
    client = environment.create_client()

    with pytest.raises(MCPConnectionError):
        await client.connect()

    assert client.is_ready is False
    assert environment.transport.exit_count == 1
    assert environment.session.exit_count == 1

    await client.close()
    await client.close()


async def test_reconnect_replaces_and_closes_lost_session(
) -> None:
    """Ferme l'ancienne génération avant de restaurer la connexion."""

    environment = SequencedMCPEnvironment()
    client = environment.create_client()
    await client.connect()
    first_session = environment.sessions[0]
    first_session.ping_error = httpx.ConnectError(
        "Session MCP perdue."
    )

    assert await client.check_connection() is False
    assert await client.ensure_connected() is True
    assert client.is_ready is True
    assert len(environment.sessions) == 2
    assert environment.sessions[1] is not first_session
    assert first_session.exit_count == 1
    assert environment.transports[0].exit_count == 1

    await client.close()


async def test_concurrent_reconnect_creates_only_one_session(
) -> None:
    """Sérialise plusieurs récupérations sur le verrou dédié."""

    environment = SequencedMCPEnvironment()
    client = environment.create_client()
    await client.connect()
    environment.sessions[0].ping_error = httpx.ConnectError(
        "Session MCP perdue."
    )
    assert await client.check_connection() is False

    results = await asyncio.gather(
        *(client.ensure_connected() for _ in range(5))
    )

    assert results == [True] * 5
    assert len(environment.sessions) == 2
    assert len(environment.transports) == 2

    await client.close()


async def test_reconnect_respects_attempts_and_bounded_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Épuise exactement trois essais avec un délai plafonné."""

    environment = SequencedMCPEnvironment(failures=10)
    client = environment.create_client(
        attempts=3,
        initial_delay=0.25,
        max_delay=0.3,
    )
    observed_delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        observed_delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)

    assert await client.ensure_connected() is False
    assert len(environment.sessions) == 3
    assert len(environment.transports) == 3
    assert observed_delays == [0.25, 0.3]
    assert client.is_ready is False

    await client.close()
    await client.close()


async def test_external_connect_cancellation_is_not_masked() -> None:
    """Propage l'annulation appelante et ferme les contextes ouverts."""

    environment = FakeMCPEnvironment()
    initialize_started = asyncio.Event()
    release_initialize = asyncio.Event()

    async def blocking_initialize() -> None:
        environment.session.initialize_count += 1
        initialize_started.set()
        await release_initialize.wait()

    environment.session.initialize = blocking_initialize
    client = environment.create_client()
    connect_task = asyncio.create_task(client.connect())
    await initialize_started.wait()
    connect_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await connect_task

    assert client.is_ready is False
    assert environment.transport.exit_count == 1
    assert environment.session.exit_count == 1

    await client.close()


@pytest.mark.parametrize(
    ("tool_names", "expected_exception"),
    [
        (
            sorted(EXPECTED_TOOLS - {"list_products"}),
            MCPToolNotFoundError,
        ),
        (
            sorted(EXPECTED_TOOLS) + ["unexpected_tool"],
            MCPProtocolError,
        ),
        (
            sorted(EXPECTED_TOOLS) + ["list_products"],
            MCPProtocolError,
        ),
        (
            "not-a-list",
            MCPProtocolError,
        ),
    ],
)
async def test_connect_rejects_invalid_tool_lists(
    tool_names: object,
    expected_exception: type[Exception],
) -> None:
    """Refuse les listes incomplètes, étendues, dupliquées ou invalides."""

    environment = FakeMCPEnvironment(tool_names)
    client = environment.create_client()

    with pytest.raises(expected_exception):
        await client.connect()

    assert client.is_ready is False
    assert environment.session.exit_count == 1
    assert environment.transport.exit_count == 1


async def test_connect_rejects_invalid_tool_name() -> None:
    """Refuse un outil dont le nom n'est pas une chaîne non vide."""

    environment = FakeMCPEnvironment()
    environment.session.tools[0] = SimpleNamespace(name=" ")
    client = environment.create_client()

    with pytest.raises(MCPProtocolError):
        await client.connect()

    assert client.is_ready is False


async def test_connect_rejects_paginated_tool_list() -> None:
    """Refuse une liste dont l'exactitude ne peut pas être établie."""

    environment = FakeMCPEnvironment()
    environment.session.next_cursor = "next-page"
    client = environment.create_client()

    with pytest.raises(MCPProtocolError):
        await client.connect()

    assert client.is_ready is False
    assert environment.session.exit_count == 1
    assert environment.transport.exit_count == 1


async def test_connect_and_close_are_idempotent() -> None:
    """Ne crée et ne ferme qu'une session malgré les doubles appels."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    await client.connect()
    await client.connect()
    await client.close()
    await client.close()

    assert environment.transport_factory_count == 1
    assert environment.session_factory_count == 1
    assert environment.session.exit_count == 1
    assert environment.transport.exit_count == 1
    assert client.is_ready is False


async def test_connection_error_is_local_and_closes_partial_state() -> None:
    """Traduit l'erreur SDK et ferme le transport déjà ouvert."""

    environment = FakeMCPEnvironment()
    environment.session.initialize_error = McpError(
        ErrorData(
            code=-32603,
            message="technical initialization content",
        )
    )
    client = environment.create_client()

    with pytest.raises(MCPConnectionError) as exception:
        await client.connect()

    assert "technical initialization content" not in str(
        exception.value
    )
    assert client.is_ready is False
    assert environment.session.exit_count == 1
    assert environment.transport.exit_count == 1


async def test_unexpected_connection_bug_is_not_masked() -> None:
    """Laisse remonter un bug Python pendant l'initialisation."""

    environment = FakeMCPEnvironment()
    environment.session.initialize_error = RuntimeError(
        "bug d'initialisation"
    )
    client = environment.create_client()

    with pytest.raises(RuntimeError, match="bug d'initialisation"):
        await client.connect()

    assert client.is_ready is False
    assert environment.session.exit_count == 1
    assert environment.transport.exit_count == 1


async def test_async_context_manager_closes_session() -> None:
    """Prend en charge la syntaxe async with."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    async with client as connected_client:
        assert connected_client is client
        assert client.is_ready is True

    assert client.is_ready is False
    assert environment.session.exit_count == 1


async def test_call_refuses_disconnected_client() -> None:
    """Retourne une erreur locale avant tout échange sans session."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    with pytest.raises(MCPConnectionError):
        await client.list_products()

    assert environment.session.calls == []


async def test_call_refuses_tool_outside_allowlist() -> None:
    """Refuse un nom interne absent de l'allowlist."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()
    await client.connect()

    with pytest.raises(MCPToolNotFoundError):
        await client._call_tool("delete_stock", {})

    assert environment.session.calls == []

    await client.close()


@pytest.mark.parametrize(
    "tool_result",
    [
        SimpleNamespace(isError=False, structuredContent=None),
        SimpleNamespace(isError=False, structuredContent="invalid"),
        SimpleNamespace(
            isError=False,
            structuredContent={"other": {}},
        ),
        SimpleNamespace(
            isError=False,
            structuredContent={
                "result": {},
                "extra": {},
            },
        ),
        SimpleNamespace(
            isError=False,
            structuredContent={"result": []},
        ),
        SimpleNamespace(
            isError=True,
            structuredContent={"result": {}},
        ),
    ],
)
async def test_call_rejects_invalid_protocol_envelopes(
    tool_result: SimpleNamespace,
) -> None:
    """Refuse toutes les enveloppes non conformes au protocole."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    async def handler(
        _name: str,
        _arguments: dict[str, object],
    ) -> SimpleNamespace:
        return tool_result

    environment.session.call_handler = handler
    await client.connect()

    with pytest.raises(MCPProtocolError):
        await client.list_products()

    await client.close()


async def test_business_error_becomes_local_exception() -> None:
    """Conserve le nom et le code sans exposer le message distant."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    async def handler(
        _name: str,
        _arguments: dict[str, object],
    ) -> SimpleNamespace:
        return tool_call_result(
            {
                "success": False,
                "error": {
                    "code": "resource_not_found",
                    "message": "Message métier distant.",
                },
            }
        )

    environment.session.call_handler = handler
    await client.connect()

    with pytest.raises(MCPToolResponseError) as exception:
        await client.get_product_details(12)

    assert exception.value.tool_name == "get_product_details"
    assert exception.value.code == "resource_not_found"
    assert "Message métier distant" not in str(exception.value)

    await client.close()


@pytest.mark.parametrize(
    "invalid_result",
    [
        {
            **SUCCESS_RESULTS["list_products"],
            "unexpected": True,
        },
        {
            **SUCCESS_RESULTS["list_products"],
            "count": -1,
        },
        {
            "success": "true",
            "count": 0,
            "limit": 20,
            "offset": 0,
            "products": [],
            "error": None,
        },
        {
            "success": 1,
            "count": 0,
            "limit": 20,
            "offset": 0,
            "products": [],
            "error": None,
        },
    ],
)
async def test_success_response_is_strictly_validated(
    invalid_result: dict[str, object],
) -> None:
    """Refuse un champ supplémentaire ou une donnée mal typée."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    async def handler(
        _name: str,
        _arguments: dict[str, object],
    ) -> SimpleNamespace:
        return tool_call_result(invalid_result)

    environment.session.call_handler = handler
    await client.connect()

    with pytest.raises(MCPProtocolError):
        await client.list_products()

    await client.close()


async def test_five_methods_call_exact_tools_and_return_models() -> None:
    """Vérifie les noms, arguments et types des cinq méthodes."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()
    await client.connect()

    products = await client.list_products(limit=20, offset=0)
    details = await client.get_product_details(12)
    by_product = await client.get_stock_by_product(12)
    by_branch = await client.get_stock_by_branch(1)
    shopping = await client.check_shopping_list(
        [
            ShoppingListItem(
                product_id=12,
                quantity=2,
            )
        ]
    )

    assert isinstance(products, ProductListData)
    assert isinstance(details, ProductDetailsData)
    assert isinstance(by_product, StockByProductData)
    assert isinstance(by_branch, StockByBranchData)
    assert isinstance(shopping, ShoppingListData)
    assert environment.session.calls == [
        (
            "list_products",
            {
                "limit": 20,
                "offset": 0,
            },
        ),
        (
            "get_product_details",
            {
                "product_id": 12,
            },
        ),
        (
            "get_stock_by_product",
            {
                "product_id": 12,
            },
        ),
        (
            "get_stock_by_branch",
            {
                "branch_id": 1,
            },
        ),
        (
            "check_shopping_list",
            {
                "items": [
                    {
                        "product_id": 12,
                        "quantity": 2,
                    },
                ],
            },
        ),
    ]

    await client.close()


async def test_stock_by_branch_accepts_name() -> None:
    """Transmet un nom normalisé au même outil MCP."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()
    await client.connect()

    result = await client.get_stock_by_branch(
        branch_name="  Toulouse  "
    )

    assert isinstance(result, StockByBranchData)
    assert environment.session.calls[-1] == (
        "get_stock_by_branch",
        {
            "branch_name": "Toulouse",
        },
    )

    await client.close()


async def test_shopping_list_preserves_duplicates() -> None:
    """Ne modifie pas silencieusement la liste transmise au serveur."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()
    await client.connect()

    await client.check_shopping_list(
        [
            ShoppingListItem(product_id=12, quantity=1),
            ShoppingListItem(product_id=12, quantity=2),
        ]
    )

    assert environment.session.calls[-1] == (
        "check_shopping_list",
        {
            "items": [
                {
                    "product_id": 12,
                    "quantity": 1,
                },
                {
                    "product_id": 12,
                    "quantity": 2,
                },
            ],
        },
    )

    await client.close()


@pytest.mark.parametrize(
    ("method_name", "arguments"),
    [
        ("list_products", {"limit": 0}),
        ("list_products", {"limit": 101}),
        ("list_products", {"limit": True}),
        ("list_products", {"offset": -1}),
        ("list_products", {"offset": False}),
        ("get_product_details", {"product_id": 0}),
        ("get_product_details", {"product_id": -1}),
        ("get_product_details", {"product_id": True}),
        ("get_stock_by_product", {"product_id": 0}),
        ("get_stock_by_branch", {"branch_id": 0}),
        ("get_stock_by_branch", {"branch_id": False}),
        ("get_stock_by_branch", {}),
        (
            "get_stock_by_branch",
            {
                "branch_id": 1,
                "branch_name": "Toulouse",
            },
        ),
        ("get_stock_by_branch", {"branch_name": ""}),
        ("check_shopping_list", {"items": []}),
        (
            "check_shopping_list",
            {
                "items": [
                    {
                        "product_id": 12,
                        "quantity": 0,
                    }
                ],
            },
        ),
        (
            "check_shopping_list",
            {
                "items": [
                    {
                        "product_id": 12,
                        "quantity": 1,
                        "extra": True,
                    }
                ],
            },
        ),
    ],
)
async def test_invalid_arguments_never_reach_session(
    method_name: str,
    arguments: dict[str, object],
) -> None:
    """Valide tous les arguments localement avant l'appel MCP."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()
    await client.connect()
    method = getattr(client, method_name)

    with pytest.raises(MCPInvalidArgumentError):
        await method(**arguments)

    assert environment.session.calls == []

    await client.close()


async def test_timeout_becomes_local_exception() -> None:
    """Convertit un timeout HTTP en erreur MCP locale."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    async def handler(
        _name: str,
        _arguments: dict[str, object],
    ) -> SimpleNamespace:
        raise httpx.ReadTimeout("technical transport content")

    environment.session.call_handler = handler
    await client.connect()

    with pytest.raises(MCPTimeoutError) as exception:
        await client.list_products()

    assert "technical transport content" not in str(exception.value)

    await client.close()


async def test_sdk_timeout_becomes_local_exception() -> None:
    """Convertit aussi le timeout officiel du SDK MCP."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    async def handler(
        _name: str,
        _arguments: dict[str, object],
    ) -> SimpleNamespace:
        raise McpError(
            ErrorData(
                code=408,
                message="technical SDK content",
            )
        )

    environment.session.call_handler = handler
    await client.connect()

    with pytest.raises(MCPTimeoutError) as exception:
        await client.list_products()

    assert "technical SDK content" not in str(exception.value)

    await client.close()


async def test_sdk_protocol_error_becomes_local_exception() -> None:
    """Empêche une erreur brute du SDK de traverser le client."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    async def handler(
        _name: str,
        _arguments: dict[str, object],
    ) -> SimpleNamespace:
        raise McpError(
            ErrorData(
                code=-32603,
                message="technical SDK content",
            )
        )

    environment.session.call_handler = handler
    await client.connect()

    with pytest.raises(MCPProtocolError) as exception:
        await client.list_products()

    assert "technical SDK content" not in str(exception.value)

    await client.close()


async def test_configured_timeout_limits_each_tool_call() -> None:
    """Applique aussi un timeout local à chaque appel d'outil."""

    environment = FakeMCPEnvironment()
    client = environment.create_client(timeout=0.01)

    async def handler(
        _name: str,
        _arguments: dict[str, object],
    ) -> SimpleNamespace:
        await asyncio.Event().wait()
        raise AssertionError("La coroutine aurait dû être annulée.")

    environment.session.call_handler = handler
    await client.connect()

    with pytest.raises(MCPTimeoutError):
        await client.list_products()

    await client.close()


async def test_semaphore_limits_concurrent_calls() -> None:
    """N'autorise pas plus d'appels simultanés que la limite."""

    environment = FakeMCPEnvironment()
    client = environment.create_client(concurrency=2)
    release = asyncio.Event()
    two_calls_started = asyncio.Event()
    active_calls = 0
    maximum_active_calls = 0

    async def handler(
        _name: str,
        _arguments: dict[str, object],
    ) -> SimpleNamespace:
        nonlocal active_calls, maximum_active_calls

        active_calls += 1
        maximum_active_calls = max(
            maximum_active_calls,
            active_calls,
        )

        if active_calls == 2:
            two_calls_started.set()

        try:
            await release.wait()
            return tool_call_result(
                SUCCESS_RESULTS["list_products"]
            )
        finally:
            active_calls -= 1

    environment.session.call_handler = handler
    await client.connect()

    calls = [
        asyncio.create_task(client.list_products())
        for _ in range(3)
    ]

    await asyncio.wait_for(two_calls_started.wait(), timeout=1)
    await asyncio.sleep(0)

    assert maximum_active_calls == 2
    assert len(environment.session.calls) == 2

    release.set()
    await asyncio.gather(*calls)

    assert maximum_active_calls == 2
    assert environment.session_factory_count == 1

    await client.close()


async def test_unexpected_python_bug_is_not_masked() -> None:
    """Laisse remonter une erreur Python qui n'est pas un incident MCP."""

    environment = FakeMCPEnvironment()
    client = environment.create_client()

    async def handler(
        _name: str,
        _arguments: dict[str, object],
    ) -> SimpleNamespace:
        raise RuntimeError("bug inattendu")

    environment.session.call_handler = handler
    await client.connect()

    with pytest.raises(RuntimeError, match="bug inattendu"):
        await client.list_products()

    await client.close()
