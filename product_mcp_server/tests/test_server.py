#!/usr/bin/env python3
"""Tests d'intégration du serveur MCP HBntory."""

from typing import Any

import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session,
)

import server as server_module
from config import Settings


PRODUCT = {
    "id": 12,
    "sku": "HB-TEST-0012",
    "name": "Produit de test",
    "description": "Description du produit.",
    "category": "Tests",
    "brand": "HBntory",
    "supplier_id": "SUP-TEST-001",
    "supplier_name": "Fournisseur de test",
    "unit_price": 49.99,
    "currency": "EUR",
    "discontinued": False,
    "weight_kg": 1.25,
    "tags": [
        "test",
        "mcp",
    ],
    "updated_at": "2026-07-24T12:00:00Z",
    "supplier": None,
}


class FakeProductAPIClient:
    """Remplace le véritable client Produit pendant les tests."""

    instances = []

    def __init__(self, base_url: str) -> None:
        """Enregistre la configuration reçue."""

        self.base_url = base_url
        self.closed = False

        self.__class__.instances.append(self)

    async def list_products(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Retourne une page Produit fictive."""

        return {
            "count": 1,
            "limit": limit,
            "offset": offset,
            "results": [PRODUCT],
        }

    async def get_product_details(
        self,
        product_id: int,
    ) -> dict[str, Any]:
        """Retourne un produit fictif."""

        return {
            **PRODUCT,
            "id": product_id,
        }

    async def aclose(self) -> None:
        """Indique que le client a été fermé."""

        self.closed = True


class FakeBackofficeAPIClient:
    """Remplace le véritable client Backoffice pendant les tests."""

    instances = []

    def __init__(
        self,
        base_url: str,
        internal_api_key: str,
    ) -> None:
        """Enregistre la configuration reçue."""

        self.base_url = base_url
        self.internal_api_key = internal_api_key
        self.closed = False

        self.__class__.instances.append(self)

    async def get_stock_by_product(
        self,
        product_id: int,
    ) -> dict[str, Any]:
        """Retourne les branches possédant un produit."""

        return {
            "product_id": product_id,
            "branches": [
                {
                    "branch_id": 1,
                    "branch_name": "Toulouse",
                    "quantity": 8,
                },
            ],
        }

    async def get_stock_by_branch(
        self,
        branch_id: int,
    ) -> dict[str, Any]:
        """Retourne les stocks d'une branche."""

        return {
            "branch": {
                "id": branch_id,
                "name": "Toulouse",
            },
            "stocks": [
                {
                    "product_id": 12,
                    "quantity": 8,
                },
            ],
        }

    async def check_shopping_list(
        self,
        items: list[dict[str, int]],
    ) -> dict[str, Any]:
        """Retourne les branches satisfaisant une liste."""

        matching_items = [
            {
                "product_id": item["product_id"],
                "requested_quantity": item["quantity"],
                "available_quantity": 8,
            }
            for item in items
        ]

        return {
            "matching_branches": [
                {
                    "branch_id": 1,
                    "branch_name": "Toulouse",
                    "items": matching_items,
                },
            ],
        }

    async def aclose(self) -> None:
        """Indique que le client a été fermé."""

        self.closed = True


@pytest.fixture
def settings() -> Settings:
    """Retourne une configuration isolée pour les tests."""

    return Settings(
        product_api_base_url="http://products.test",
        backoffice_internal_url="http://backoffice.test",
        internal_api_key="x" * 32,
        mcp_host="127.0.0.1",
        mcp_port=8000,
    )


@pytest.fixture
def mcp_server(
    monkeypatch,
    settings: Settings,
):
    """Crée un serveur utilisant uniquement les faux clients."""

    FakeProductAPIClient.instances.clear()
    FakeBackofficeAPIClient.instances.clear()

    monkeypatch.setattr(
        server_module,
        "ProductAPIClient",
        FakeProductAPIClient,
    )
    monkeypatch.setattr(
        server_module,
        "BackofficeAPIClient",
        FakeBackofficeAPIClient,
    )

    return server_module.create_server(settings)


def get_structured_content(result) -> dict[str, Any]:
    """Extrait et valide le résultat métier d'un outil MCP."""

    assert result.isError is False
    assert result.structuredContent is not None

    structured_content = result.structuredContent

    assert isinstance(structured_content, dict)

    # FastMCP enveloppe une union de modèles sous la clé result.
    if set(structured_content) == {"result"}:
        tool_result = structured_content["result"]

        assert isinstance(tool_result, dict)

        return tool_result

    return structured_content


@pytest.mark.asyncio
async def test_server_registers_five_expected_tools(mcp_server):
    """Expose uniquement les cinq outils prévus par l'architecture."""

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ) as session:
        result = await session.list_tools()

    tool_names = {
        tool.name
        for tool in result.tools
    }

    assert tool_names == {
        "list_products",
        "get_product_details",
        "get_stock_by_product",
        "get_stock_by_branch",
        "check_shopping_list",
    }


@pytest.mark.asyncio
async def test_list_products_through_mcp_protocol(mcp_server):
    """Appelle list_products à travers une vraie session MCP."""

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            "list_products",
            {
                "limit": 10,
                "offset": 5,
            },
        )

    content = get_structured_content(result)

    assert content == {
        "success": True,
        "count": 1,
        "limit": 10,
        "offset": 5,
        "products": [PRODUCT],
        "error": None,
    }


@pytest.mark.asyncio
async def test_get_product_details_through_mcp_protocol(
    mcp_server,
):
    """Appelle get_product_details via le protocole MCP."""

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            "get_product_details",
            {
                "product_id": 12,
            },
        )

    content = get_structured_content(result)

    assert content == {
        "success": True,
        "product": PRODUCT,
        "error": None,
    }


@pytest.mark.asyncio
async def test_get_stock_by_product_through_mcp_protocol(
    mcp_server,
):
    """Appelle get_stock_by_product via le protocole MCP."""

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            "get_stock_by_product",
            {
                "product_id": 12,
            },
        )

    content = get_structured_content(result)

    assert content == {
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
    }


@pytest.mark.asyncio
async def test_get_stock_by_branch_through_mcp_protocol(
    mcp_server,
):
    """Appelle get_stock_by_branch via le protocole MCP."""

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            "get_stock_by_branch",
            {
                "branch_id": 1,
            },
        )

    content = get_structured_content(result)

    assert content == {
        "success": True,
        "branch": {
            "id": 1,
            "name": "Toulouse",
        },
        "stocks": [
            {
                "product_id": 12,
                "quantity": 8,
            },
        ],
        "error": None,
    }


@pytest.mark.asyncio
async def test_check_shopping_list_through_mcp_protocol(
    mcp_server,
):
    """Appelle check_shopping_list via le protocole MCP."""

    items = [
        {
            "product_id": 12,
            "quantity": 3,
        },
    ]

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            "check_shopping_list",
            {
                "items": items,
            },
        )

    content = get_structured_content(result)

    assert content == {
        "success": True,
        "matching_branches": [
            {
                "branch_id": 1,
                "branch_name": "Toulouse",
                "items": [
                    {
                        "product_id": 12,
                        "requested_quantity": 3,
                        "available_quantity": 8,
                    },
                ],
            },
        ],
        "error": None,
    }


@pytest.mark.asyncio
async def test_clients_are_closed_when_server_stops(mcp_server):
    """Ferme les deux clients à la fin du cycle de vie MCP."""

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ):
        product_client = FakeProductAPIClient.instances[-1]
        backoffice_client = FakeBackofficeAPIClient.instances[-1]

        assert product_client.closed is False
        assert backoffice_client.closed is False

    assert product_client.closed is True
    assert backoffice_client.closed is True


async def get_registered_tools(mcp_server) -> dict:
    """Retourne les outils enregistrés, indexés par leur nom."""

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ) as session:
        result = await session.list_tools()

    return {
        tool.name: tool
        for tool in result.tools
    }


@pytest.mark.asyncio
async def test_list_products_input_schema_is_constrained(
    mcp_server,
):
    """Expose les contraintes de pagination dans le schéma MCP."""

    tools = await get_registered_tools(mcp_server)
    schema = tools["list_products"].inputSchema

    limit_schema = schema["properties"]["limit"]
    offset_schema = schema["properties"]["offset"]

    assert limit_schema["minimum"] == 1
    assert limit_schema["maximum"] == 100
    assert limit_schema["type"] == "integer"

    assert offset_schema["minimum"] == 0
    assert offset_schema["type"] == "integer"


@pytest.mark.asyncio
async def test_identifiers_are_positive_in_mcp_schemas(
    mcp_server,
):
    """Expose des identifiants strictement positifs."""

    tools = await get_registered_tools(mcp_server)

    product_schema = tools[
        "get_product_details"
    ].inputSchema["properties"]["product_id"]

    branch_schema = tools[
        "get_stock_by_branch"
    ].inputSchema["properties"]["branch_id"]

    assert product_schema["exclusiveMinimum"] == 0
    assert product_schema["type"] == "integer"

    assert branch_schema["exclusiveMinimum"] == 0
    assert branch_schema["type"] == "integer"


@pytest.mark.asyncio
async def test_shopping_list_input_schema_is_strict(
    mcp_server,
):
    """Décrit précisément chaque article de la liste d'achats."""

    tools = await get_registered_tools(mcp_server)
    schema = tools["check_shopping_list"].inputSchema

    items_schema = schema["properties"]["items"]

    assert items_schema["type"] == "array"
    assert items_schema["minItems"] == 1

    item_reference = items_schema["items"]["$ref"]

    assert item_reference == (
        "#/$defs/ShoppingListItemInput"
    )

    item_schema = schema["$defs"][
        "ShoppingListItemInput"
    ]

    assert item_schema["additionalProperties"] is False
    assert set(item_schema["required"]) == {
        "product_id",
        "quantity",
    }

    assert (
        item_schema["properties"]["product_id"][
            "exclusiveMinimum"
        ]
        == 0
    )

    assert (
        item_schema["properties"]["quantity"][
            "exclusiveMinimum"
        ]
        == 0
    )


@pytest.mark.asyncio
async def test_shopping_list_output_schema_is_explicit(
    mcp_server,
):
    """Expose une sortie structurée et fermée."""

    tools = await get_registered_tools(mcp_server)
    schema = tools["check_shopping_list"].outputSchema

    success_schema = schema["$defs"][
        "ShoppingListSuccess"
    ]
    branch_schema = schema["$defs"][
        "MatchingBranchSchema"
    ]
    item_schema = schema["$defs"][
        "MatchingItemSchema"
    ]

    assert success_schema["additionalProperties"] is False
    assert branch_schema["additionalProperties"] is False
    assert item_schema["additionalProperties"] is False

    assert set(success_schema["required"]) == {
        "success",
        "matching_branches",
    }

    assert set(branch_schema["required"]) == {
        "branch_id",
        "branch_name",
        "items",
    }

    assert set(item_schema["required"]) == {
        "product_id",
        "requested_quantity",
        "available_quantity",
    }


@pytest.mark.asyncio
async def test_empty_shopping_list_is_rejected_by_mcp(
    mcp_server,
):
    """Refuse une liste vide avant l'appel au Backoffice."""

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            "check_shopping_list",
            {
                "items": [],
            },
        )

    assert result.isError is True
    assert result.structuredContent is None


@pytest.mark.asyncio
async def test_malformed_product_returns_structured_mcp_error(
    monkeypatch,
    settings: Settings,
):
    """Transforme un produit malformé en erreur MCP structurée."""

    import httpx

    from clients.product_api import ProductAPIClient

    class MalformedProductAPIClient(ProductAPIClient):
        """Client Produit réel connecté à une réponse HTTP malformée."""

        def __init__(self, base_url: str) -> None:
            """Configure un faux transport HTTP sans réseau."""

            def handler(_request):
                malformed_product = {
                    **PRODUCT,
                    "brand": 123,
                }

                return httpx.Response(
                    200,
                    json=malformed_product,
                )

            transport = httpx.MockTransport(handler)

            self._mock_http_client = httpx.AsyncClient(
                transport=transport,
            )

            super().__init__(
                base_url,
                http_client=self._mock_http_client,
            )

        async def aclose(self) -> None:
            """Ferme le faux client HTTP."""

            await self._mock_http_client.aclose()

    monkeypatch.setattr(
        server_module,
        "ProductAPIClient",
        MalformedProductAPIClient,
    )

    mcp = server_module.create_server(settings)

    async with create_connected_server_and_client_session(
        mcp,
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            "get_product_details",
            {
                "product_id": 12,
            },
        )

    assert result.isError is False
    assert result.structuredContent is not None

    payload = result.structuredContent["result"]

    assert payload == {
        "success": False,
        "error": {
            "code": "invalid_service_response",
            "message": (
                "Un produit retourné par l'API Produit "
                "ne respecte pas le contrat attendu."
            ),
        },
    }


@pytest.mark.asyncio
async def test_root_input_schemas_are_strict(mcp_server):
    """Interdit les propriétés supplémentaires à la racine."""

    tools = await get_registered_tools(mcp_server)

    expected_tool_names = {
        "list_products",
        "get_product_details",
        "get_stock_by_product",
        "get_stock_by_branch",
        "check_shopping_list",
    }

    for tool_name in expected_tool_names:
        input_schema = tools[tool_name].inputSchema

        assert input_schema["additionalProperties"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            "list_products",
            {
                "limit": 10,
                "offset": 0,
                "unexpected": 1,
            },
        ),
        (
            "get_product_details",
            {
                "product_id": 12,
                "unexpected": 1,
            },
        ),
        (
            "get_stock_by_product",
            {
                "product_id": 12,
                "unexpected": 1,
            },
        ),
        (
            "get_stock_by_branch",
            {
                "branch_id": 1,
                "unexpected": 1,
            },
        ),
        (
            "check_shopping_list",
            {
                "items": [
                    {
                        "product_id": 12,
                        "quantity": 1,
                    },
                ],
                "unexpected": 1,
            },
        ),
    ],
)
async def test_tools_reject_unknown_root_argument(
    mcp_server,
    tool_name,
    arguments,
):
    """Refuse un argument inconnu avant l'exécution de l'outil."""

    async with create_connected_server_and_client_session(
        mcp_server,
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            tool_name,
            arguments,
        )

    assert result.isError is True
    assert result.structuredContent is None
