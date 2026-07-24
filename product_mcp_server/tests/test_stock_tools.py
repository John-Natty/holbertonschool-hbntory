#!/usr/bin/env python3
"""Tests des outils MCP de consultation des stocks."""

from unittest.mock import AsyncMock

import pytest

from clients.errors import (
    ExternalServiceResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    InvalidClientParameterError,
    ResourceNotFoundError,
)
from tools.stock_tools import (
    check_shopping_list_tool,
    get_stock_by_branch_tool,
    get_stock_by_product_tool,
)


@pytest.mark.asyncio
async def test_get_stock_by_product_returns_success():
    """Retourne les branches possédant le produit demandé."""

    client = AsyncMock()
    client.get_stock_by_product.return_value = {
        "product_id": 12,
        "branches": [
            {
                "branch_id": 1,
                "branch_name": "Toulouse",
                "quantity": 8,
            },
        ],
    }

    result = await get_stock_by_product_tool(
        client,
        product_id=12,
    )

    assert result == {
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

    client.get_stock_by_product.assert_awaited_once_with(12)


@pytest.mark.asyncio
async def test_get_stock_by_branch_returns_success():
    """Retourne les produits disponibles dans une branche."""

    client = AsyncMock()
    client.get_stock_by_branch.return_value = {
        "branch": {
            "id": 1,
            "name": "Toulouse",
        },
        "stocks": [
            {
                "product_id": 12,
                "quantity": 8,
            },
            {
                "product_id": 25,
                "quantity": 4,
            },
        ],
    }

    result = await get_stock_by_branch_tool(
        client,
        branch_id=1,
    )

    assert result == {
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
            {
                "product_id": 25,
                "quantity": 4,
            },
        ],
        "error": None,
    }

    client.get_stock_by_branch.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_check_shopping_list_returns_success():
    """Retourne les branches pouvant satisfaire toute la liste."""

    requested_items = [
        {
            "product_id": 12,
            "quantity": 3,
        },
        {
            "product_id": 25,
            "quantity": 2,
        },
    ]

    client = AsyncMock()
    client.check_shopping_list.return_value = {
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
                    {
                        "product_id": 25,
                        "requested_quantity": 2,
                        "available_quantity": 4,
                    },
                ],
            },
        ],
    }

    result = await check_shopping_list_tool(
        client,
        items=requested_items,
    )

    assert result == {
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
                    {
                        "product_id": 25,
                        "requested_quantity": 2,
                        "available_quantity": 4,
                    },
                ],
            },
        ],
        "error": None,
    }

    client.check_shopping_list.assert_awaited_once_with(
        requested_items
    )


@pytest.mark.asyncio
async def test_invalid_parameters_are_transformed():
    """Transforme une erreur de paramètre en réponse structurée."""

    client = AsyncMock()
    client.get_stock_by_product.side_effect = (
        InvalidClientParameterError(
            "product_id doit être un entier strictement positif."
        )
    )

    result = await get_stock_by_product_tool(
        client,
        product_id=0,
    )

    assert result == {
        "success": False,
        "error": {
            "code": "invalid_parameters",
            "message": (
                "product_id doit être un entier "
                "strictement positif."
            ),
        },
    }


@pytest.mark.asyncio
async def test_missing_branch_is_transformed():
    """Transforme une branche inexistante en réponse structurée."""

    client = AsyncMock()
    client.get_stock_by_branch.side_effect = (
        ResourceNotFoundError(
            "La branche demandée n'existe pas."
        )
    )

    result = await get_stock_by_branch_tool(
        client,
        branch_id=999999,
    )

    assert result == {
        "success": False,
        "error": {
            "code": "resource_not_found",
            "message": "La branche demandée n'existe pas.",
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            ExternalServiceTimeoutError(
                "Le Backoffice a dépassé le délai de réponse."
            ),
            "service_timeout",
        ),
        (
            ExternalServiceUnavailableError(
                "Le Backoffice est injoignable."
            ),
            "service_unavailable",
        ),
        (
            ExternalServiceResponseError(
                "La réponse du Backoffice est invalide."
            ),
            "invalid_service_response",
        ),
    ],
)
async def test_backoffice_errors_are_transformed(
    error,
    expected_code,
):
    """Transforme les pannes du Backoffice en réponses MCP."""

    client = AsyncMock()
    client.check_shopping_list.side_effect = error

    result = await check_shopping_list_tool(
        client,
        items=[
            {
                "product_id": 12,
                "quantity": 1,
            },
        ],
    )

    assert result["success"] is False
    assert result["error"]["code"] == expected_code
    assert result["error"]["message"] == str(error)


@pytest.mark.asyncio
async def test_unexpected_python_error_is_not_hidden():
    """Laisse remonter un bug inattendu pour faciliter son diagnostic."""

    client = AsyncMock()
    client.get_stock_by_branch.side_effect = RuntimeError(
        "Bug inattendu"
    )

    with pytest.raises(
        RuntimeError,
        match="Bug inattendu",
    ):
        await get_stock_by_branch_tool(
            client,
            branch_id=1,
        )
