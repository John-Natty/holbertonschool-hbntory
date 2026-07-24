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
    "unit_price": 49.99,
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
    """Extrait et valide le résultat structuré d'un outil MCP."""

    assert result.isError is False
    assert result.structuredContent is not None

    return result.structuredContent


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
