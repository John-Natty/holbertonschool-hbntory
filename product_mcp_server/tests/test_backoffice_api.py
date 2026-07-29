#!/usr/bin/env python3
"""Tests du client asynchrone de l'API interne Backoffice."""

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from clients.backoffice_api import BackofficeAPIClient
from clients.errors import (
    ExternalServiceResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    InvalidClientParameterError,
    ResourceNotFoundError,
)


INTERNAL_API_KEY = (
    "cle-interne-reservee-aux-tests-hbntory"
)


@asynccontextmanager
async def create_test_client(handler):
    """Crée un client utilisant uniquement un transport HTTP mocké."""

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as http_client:
        yield BackofficeAPIClient(
            "http://backoffice.test",
            INTERNAL_API_KEY,
            http_client=http_client,
        )


@pytest.mark.asyncio
async def test_get_stock_by_product_returns_branches():
    """Retourne les branches possédant le produit demandé."""

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == (
            "/internal/stocks/products/12"
        )
        assert request.headers["X-Internal-API-Key"] == (
            INTERNAL_API_KEY
        )

        return httpx.Response(
            200,
            json={
                "success": True,
                "product_id": 12,
                "branches": [
                    {
                        "branch_id": 1,
                        "branch_name": "Toulouse",
                        "quantity": 8,
                    },
                    {
                        "branch_id": 2,
                        "branch_name": "Carcassonne",
                        "quantity": 3,
                    },
                ],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        result = await client.get_stock_by_product(12)

    assert result == {
        "product_id": 12,
        "branches": [
            {
                "branch_id": 1,
                "branch_name": "Toulouse",
                "quantity": 8,
            },
            {
                "branch_id": 2,
                "branch_name": "Carcassonne",
                "quantity": 3,
            },
        ],
    }


@pytest.mark.asyncio
async def test_get_stock_by_product_accepts_empty_list():
    """Accepte un produit qui n'est présent dans aucune branche."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "product_id": 12,
                "branches": [],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        result = await client.get_stock_by_product(12)

    assert result["product_id"] == 12
    assert result["branches"] == []


@pytest.mark.asyncio
async def test_get_stock_by_branch_returns_stocks():
    """Retourne les produits disponibles dans une branche."""

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == (
            "/internal/stocks/branches/1"
        )
        assert request.headers["X-Internal-API-Key"] == (
            INTERNAL_API_KEY
        )

        return httpx.Response(
            200,
            json={
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
            },
        )

    async with create_test_client(handler) as client:
        result = await client.get_stock_by_branch(1)

    assert result == {
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


@pytest.mark.asyncio
async def test_get_stock_by_branch_accepts_empty_stock():
    """Accepte une branche existante ne possédant aucun stock."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "branch": {
                    "id": 1,
                    "name": "Toulouse",
                },
                "stocks": [],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        result = await client.get_stock_by_branch(1)

    assert result["stocks"] == []


@pytest.mark.asyncio
async def test_get_stock_by_branch_resolves_normalized_name():
    """Transmet un nom normalisé à la route interne dédiée."""

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == (
            "/internal/stocks/branches/by-name"
        )
        assert request.url.params["name"] == "Toulouse"
        assert request.headers["X-Internal-API-Key"] == (
            INTERNAL_API_KEY
        )

        return httpx.Response(
            200,
            json={
                "success": True,
                "branch": {
                    "id": 1,
                    "name": "Toulouse",
                },
                "stocks": [],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        result = await client.get_stock_by_branch(
            branch_name="  Toulouse  "
        )

    assert result["branch"] == {
        "id": 1,
        "name": "Toulouse",
    }


@pytest.mark.asyncio
async def test_check_shopping_list_returns_matching_branches():
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

    def handler(request):
        assert request.method == "POST"
        assert request.url.path == (
            "/internal/stocks/check-shopping-list"
        )
        assert request.headers["X-Internal-API-Key"] == (
            INTERNAL_API_KEY
        )

        sent_data = json.loads(request.content)

        assert sent_data == {
            "items": requested_items,
        }

        return httpx.Response(
            200,
            json={
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
            },
        )

    async with create_test_client(handler) as client:
        result = await client.check_shopping_list(
            requested_items
        )

    assert result["matching_branches"][0]["branch_id"] == 1
    assert result["matching_branches"][0]["items"][0] == {
        "product_id": 12,
        "requested_quantity": 3,
        "available_quantity": 8,
    }


@pytest.mark.asyncio
async def test_check_shopping_list_accepts_no_match():
    """Accepte qu'aucune branche ne satisfasse la liste."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "matching_branches": [],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        result = await client.check_shopping_list(
            [
                {
                    "product_id": 12,
                    "quantity": 100,
                },
            ]
        )

    assert result["matching_branches"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identifier",
    [
        0,
        -1,
        True,
        "12",
        None,
    ],
)
async def test_product_identifier_is_validated(identifier):
    """Refuse un identifiant produit invalide avant l'appel HTTP."""

    async with create_test_client(
        lambda _request: pytest.fail(
            "Aucun appel HTTP ne devait être effectué."
        )
    ) as client:
        with pytest.raises(InvalidClientParameterError):
            await client.get_stock_by_product(identifier)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identifier",
    [
        0,
        -1,
        True,
        "1",
        None,
    ],
)
async def test_branch_identifier_is_validated(identifier):
    """Refuse un identifiant branche invalide avant l'appel HTTP."""

    async with create_test_client(
        lambda _request: pytest.fail(
            "Aucun appel HTTP ne devait être effectué."
        )
    ) as client:
        with pytest.raises(InvalidClientParameterError):
            await client.get_stock_by_branch(identifier)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("branch_id", "branch_name"),
    [
        (None, None),
        (1, "Toulouse"),
        (None, ""),
        (None, "   "),
        (None, 12),
    ],
)
async def test_branch_reference_is_exclusive_and_strict(
    branch_id,
    branch_name,
):
    """Refuse une référence absente, double ou un nom invalide."""

    async with create_test_client(
        lambda _request: pytest.fail(
            "Aucun appel HTTP ne devait être effectué."
        )
    ) as client:
        with pytest.raises(InvalidClientParameterError):
            await client.get_stock_by_branch(
                branch_id=branch_id,
                branch_name=branch_name,
            )


@pytest.mark.asyncio
async def test_unknown_branch_name_is_transformed():
    """Transforme aussi le 404 de la résolution par nom."""

    def handler(request):
        assert request.url.params["name"] == "Inconnue"

        return httpx.Response(
            404,
            json={
                "success": False,
                "error": {
                    "code": "branch_not_found",
                    "message": "La branche demandée n'existe pas.",
                },
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(ResourceNotFoundError):
            await client.get_stock_by_branch(
                branch_name="Inconnue"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "items",
    [
        None,
        [],
        "invalid",
        [{}],
        [
            {
                "product_id": 0,
                "quantity": 1,
            },
        ],
        [
            {
                "product_id": 1,
                "quantity": 0,
            },
        ],
        [
            {
                "product_id": 1,
                "quantity": True,
            },
        ],
    ],
)
async def test_shopping_list_parameters_are_validated(items):
    """Refuse une liste d'achats invalide avant l'appel HTTP."""

    async with create_test_client(
        lambda _request: pytest.fail(
            "Aucun appel HTTP ne devait être effectué."
        )
    ) as client:
        with pytest.raises(InvalidClientParameterError):
            await client.check_shopping_list(items)


@pytest.mark.asyncio
async def test_branch_not_found_is_transformed():
    """Transforme une réponse 404 en ResourceNotFoundError."""

    def handler(_request):
        return httpx.Response(
            404,
            json={
                "success": False,
                "error": {
                    "code": "branch_not_found",
                    "message": (
                        "La branche demandée n'existe pas."
                    ),
                },
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ResourceNotFoundError,
            match="branche demandée",
        ):
            await client.get_stock_by_branch(999999)


@pytest.mark.asyncio
async def test_invalid_internal_key_error_is_transformed():
    """Transforme le refus de la clé interne en erreur client."""

    def handler(_request):
        return httpx.Response(
            403,
            json={
                "success": False,
                "error": {
                    "code": "forbidden",
                    "message": (
                        "Clé interne absente ou incorrecte."
                    ),
                },
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="Clé interne",
        ):
            await client.get_stock_by_product(12)


@pytest.mark.asyncio
async def test_backoffice_rejects_invalid_json():
    """Refuse une réponse qui ne contient pas de JSON valide."""

    def handler(_request):
        return httpx.Response(
            200,
            content=b"not-json",
            headers={
                "content-type": "application/json",
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="JSON invalide",
        ):
            await client.get_stock_by_product(12)


@pytest.mark.asyncio
async def test_backoffice_rejects_invalid_success_value():
    """Refuse une réponse HTTP 200 indiquant un échec."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": False,
                "error": {
                    "code": "internal_error",
                    "message": "Erreur interne.",
                },
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="Erreur interne",
        ):
            await client.get_stock_by_product(12)


@pytest.mark.asyncio
async def test_backoffice_rejects_invalid_branch_structure():
    """Refuse une branche contenant un identifiant invalide."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "product_id": 12,
                "branches": [
                    {
                        "branch_id": 0,
                        "branch_name": "Toulouse",
                        "quantity": 8,
                    },
                ],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="branch_id",
        ):
            await client.get_stock_by_product(12)


@pytest.mark.asyncio
async def test_backoffice_rejects_insufficient_matching_stock():
    """Refuse une branche annoncée compatible sans assez de stock."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "matching_branches": [
                    {
                        "branch_id": 1,
                        "branch_name": "Toulouse",
                        "items": [
                            {
                                "product_id": 12,
                                "requested_quantity": 5,
                                "available_quantity": 2,
                            },
                        ],
                    },
                ],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="quantité demandée",
        ):
            await client.check_shopping_list(
                [
                    {
                        "product_id": 12,
                        "quantity": 5,
                    },
                ]
            )


@pytest.mark.asyncio
async def test_backoffice_timeout_is_transformed():
    """Transforme un dépassement du délai HTTP."""

    def handler(request):
        raise httpx.ReadTimeout(
            "Délai dépassé",
            request=request,
        )

    async with create_test_client(handler) as client:
        with pytest.raises(ExternalServiceTimeoutError):
            await client.get_stock_by_product(12)


@pytest.mark.asyncio
async def test_backoffice_network_error_is_transformed():
    """Transforme une erreur de connexion HTTP."""

    def handler(request):
        raise httpx.ConnectError(
            "Connexion impossible",
            request=request,
        )

    async with create_test_client(handler) as client:
        with pytest.raises(ExternalServiceUnavailableError):
            await client.get_stock_by_product(12)


@pytest.mark.asyncio
async def test_shopping_list_rejects_missing_requested_product():
    """Refuse une branche qui omet un produit demandé."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
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
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="tous les produits demandés",
        ):
            await client.check_shopping_list(
                [
                    {
                        "product_id": 12,
                        "quantity": 2,
                    },
                    {
                        "product_id": 25,
                        "quantity": 3,
                    },
                ]
            )


@pytest.mark.asyncio
async def test_shopping_list_rejects_added_product():
    """Refuse une branche contenant un produit supplémentaire."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
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
                            {
                                "product_id": 25,
                                "requested_quantity": 3,
                                "available_quantity": 5,
                            },
                            {
                                "product_id": 99,
                                "requested_quantity": 1,
                                "available_quantity": 4,
                            },
                        ],
                    },
                ],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="n'a pas été demandé",
        ):
            await client.check_shopping_list(
                [
                    {
                        "product_id": 12,
                        "quantity": 2,
                    },
                    {
                        "product_id": 25,
                        "quantity": 3,
                    },
                ]
            )


@pytest.mark.asyncio
async def test_shopping_list_rejects_substituted_product():
    """Refuse un produit retourné à la place d'un produit demandé."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
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
                            {
                                "product_id": 99,
                                "requested_quantity": 3,
                                "available_quantity": 6,
                            },
                        ],
                    },
                ],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="n'a pas été demandé",
        ):
            await client.check_shopping_list(
                [
                    {
                        "product_id": 12,
                        "quantity": 2,
                    },
                    {
                        "product_id": 25,
                        "quantity": 3,
                    },
                ]
            )


@pytest.mark.asyncio
async def test_shopping_list_rejects_duplicated_product():
    """Refuse un produit présent plusieurs fois dans une branche."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
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
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="produit dupliqué",
        ):
            await client.check_shopping_list(
                [
                    {
                        "product_id": 12,
                        "quantity": 2,
                    },
                ]
            )


@pytest.mark.asyncio
async def test_shopping_list_rejects_changed_requested_quantity():
    """Refuse une quantité différente de celle réellement demandée."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "matching_branches": [
                    {
                        "branch_id": 1,
                        "branch_name": "Toulouse",
                        "items": [
                            {
                                "product_id": 12,
                                "requested_quantity": 1,
                                "available_quantity": 8,
                            },
                        ],
                    },
                ],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="ne correspond pas",
        ):
            await client.check_shopping_list(
                [
                    {
                        "product_id": 12,
                        "quantity": 3,
                    },
                ]
            )


@pytest.mark.asyncio
async def test_shopping_list_normalizes_duplicate_requests():
    """Additionne les quantités demandées pour un même produit."""

    def handler(request):
        sent_data = json.loads(request.content)

        assert sent_data == {
            "items": [
                {
                    "product_id": 12,
                    "quantity": 5,
                },
                {
                    "product_id": 25,
                    "quantity": 1,
                },
            ],
        }

        return httpx.Response(
            200,
            json={
                "success": True,
                "matching_branches": [
                    {
                        "branch_id": 1,
                        "branch_name": "Toulouse",
                        "items": [
                            {
                                "product_id": 12,
                                "requested_quantity": 5,
                                "available_quantity": 8,
                            },
                            {
                                "product_id": 25,
                                "requested_quantity": 1,
                                "available_quantity": 4,
                            },
                        ],
                    },
                ],
                "error": None,
            },
        )

    async with create_test_client(handler) as client:
        result = await client.check_shopping_list(
            [
                {
                    "product_id": 12,
                    "quantity": 2,
                },
                {
                    "product_id": 12,
                    "quantity": 3,
                },
                {
                    "product_id": 25,
                    "quantity": 1,
                },
            ]
        )

    assert result["matching_branches"][0]["items"][0] == {
        "product_id": 12,
        "requested_quantity": 5,
        "available_quantity": 8,
    }
