#!/usr/bin/env python3
"""Tests des outils MCP de consultation des produits."""

from unittest.mock import AsyncMock

import pytest

from clients.errors import (
    ExternalServiceResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    InvalidClientParameterError,
    ResourceNotFoundError,
)
from tools.product_tools import (
    get_product_details_tool,
    list_products_tool,
)


def sample_product(product_id: int = 1) -> dict:
    """Retourne un produit fictif valide."""

    return {
        "id": product_id,
        "sku": f"HB-TEST-{product_id:04d}",
        "name": "Produit de test",
        "description": "Description de test.",
        "category": "Tests",
        "unit_price": 49.99,
    }


@pytest.mark.asyncio
async def test_list_products_tool_returns_structured_success():
    """Transforme une page Produit en réponse MCP réussie."""

    client = AsyncMock()
    client.list_products.return_value = {
        "count": 1,
        "limit": 20,
        "offset": 0,
        "results": [
            sample_product(),
        ],
    }

    result = await list_products_tool(
        client,
        limit=20,
        offset=0,
    )

    assert result == {
        "success": True,
        "count": 1,
        "limit": 20,
        "offset": 0,
        "products": [
            sample_product(),
        ],
        "error": None,
    }

    client.list_products.assert_awaited_once_with(
        limit=20,
        offset=0,
    )


@pytest.mark.asyncio
async def test_get_product_details_tool_returns_structured_success():
    """Retourne le produit demandé dans une réponse MCP."""

    client = AsyncMock()
    client.get_product_details.return_value = sample_product(
        product_id=12
    )

    result = await get_product_details_tool(
        client,
        product_id=12,
    )

    assert result == {
        "success": True,
        "product": sample_product(product_id=12),
        "error": None,
    }

    client.get_product_details.assert_awaited_once_with(12)


@pytest.mark.asyncio
async def test_invalid_parameters_are_transformed():
    """Transforme une erreur de paramètre en réponse structurée."""

    client = AsyncMock()
    client.list_products.side_effect = (
        InvalidClientParameterError(
            "limit doit être compris entre 1 et 100."
        )
    )

    result = await list_products_tool(
        client,
        limit=0,
    )

    assert result == {
        "success": False,
        "error": {
            "code": "invalid_parameters",
            "message": (
                "limit doit être compris entre 1 et 100."
            ),
        },
    }


@pytest.mark.asyncio
async def test_missing_product_is_transformed():
    """Transforme un produit inexistant en réponse structurée."""

    client = AsyncMock()
    client.get_product_details.side_effect = (
        ResourceNotFoundError(
            "Le produit demandé n'existe pas."
        )
    )

    result = await get_product_details_tool(
        client,
        product_id=999999,
    )

    assert result == {
        "success": False,
        "error": {
            "code": "resource_not_found",
            "message": "Le produit demandé n'existe pas.",
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            ExternalServiceTimeoutError(
                "L'API Produit a dépassé le délai."
            ),
            "service_timeout",
        ),
        (
            ExternalServiceUnavailableError(
                "L'API Produit est injoignable."
            ),
            "service_unavailable",
        ),
        (
            ExternalServiceResponseError(
                "La réponse Produit est invalide."
            ),
            "invalid_service_response",
        ),
    ],
)
async def test_service_errors_are_transformed(
    error,
    expected_code,
):
    """Transforme les pannes du service Produit en réponses MCP."""

    client = AsyncMock()
    client.list_products.side_effect = error

    result = await list_products_tool(client)

    assert result["success"] is False
    assert result["error"]["code"] == expected_code
    assert result["error"]["message"] == str(error)


@pytest.mark.asyncio
async def test_unexpected_python_error_is_not_hidden():
    """Laisse remonter un bug inattendu pour faciliter son diagnostic."""

    client = AsyncMock()
    client.list_products.side_effect = RuntimeError(
        "Bug inattendu"
    )

    with pytest.raises(
        RuntimeError,
        match="Bug inattendu",
    ):
        await list_products_tool(client)
