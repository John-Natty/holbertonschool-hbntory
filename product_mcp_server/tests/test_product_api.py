#!/usr/bin/env python3
"""Tests du client asynchrone de l'API Produit."""

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from clients.errors import (
    ExternalServiceResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    InvalidClientParameterError,
    ResourceNotFoundError,
)
from clients.product_api import ProductAPIClient


def create_json_response(payload: object) -> httpx.Response:
    """Encode un payload contrôlé, y compris les nombres non finis."""

    return httpx.Response(
        200,
        content=json.dumps(
            payload,
            allow_nan=True,
        ).encode(),
        headers={
            "content-type": "application/json",
        },
    )


def sample_supplier(reliability_score=0.99) -> dict:
    """Retourne un fournisseur fictif conforme au contrat officiel."""

    return {
        "id": "SUP-TEST-001",
        "name": "Fournisseur de test",
        "contact_email": "supplier@example.test",
        "country": "France",
        "lead_time_days": 2,
        "reliability_score": reliability_score,
    }


def sample_product(product_id: int = 1) -> dict:
    """Retourne un produit fictif conforme au contrat officiel."""

    return {
        "id": product_id,
        "sku": f"HB-TEST-{product_id:04d}",
        "name": "Produit de test",
        "description": "Description du produit de test.",
        "category": "Tests",
        "brand": "HBntory",
        "supplier_id": "SUP-TEST-001",
        "supplier_name": "Fournisseur de test",
        "unit_price": 49.99,
        "currency": "EUR",
        "discontinued": False,
        "weight_kg": 1.0,
        "tags": ["test"],
        "updated_at": "2026-07-24T12:00:00Z",
        "supplier": sample_supplier(),
    }


@asynccontextmanager
async def create_test_client(handler):
    """Crée un client utilisant uniquement un transport HTTP mocké."""

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as http_client:
        yield ProductAPIClient(
            "http://product-api.test",
            http_client=http_client,
        )


@pytest.mark.asyncio
async def test_list_products_returns_valid_page():
    """Retourne une page de produits correctement validée."""

    def handler(request):
        assert request.url.path == "/api/v1/products"
        assert request.url.params["limit"] == "20"
        assert request.url.params["offset"] == "0"

        return httpx.Response(
            200,
            json={
                "count": 1,
                "limit": 20,
                "offset": 0,
                "results": [sample_product()],
            },
        )

    async with create_test_client(handler) as client:
        result = await client.list_products()

    assert result["count"] == 1
    assert result["results"][0]["id"] == 1


@pytest.mark.asyncio
async def test_get_product_details_returns_product():
    """Retourne le produit correspondant à l'identifiant demandé."""

    def handler(request):
        assert request.url.path == "/api/v1/products/12"

        return httpx.Response(
            200,
            json=sample_product(product_id=12),
        )

    async with create_test_client(handler) as client:
        result = await client.get_product_details(12)

    assert result["id"] == 12
    assert result["name"] == "Produit de test"


@pytest.mark.asyncio
async def test_product_accepts_valid_json_numbers():
    """Accepte les entiers JSON sans borner le score fournisseur."""

    valid_product = sample_product()
    valid_product["unit_price"] = 0
    valid_product["weight_kg"] = 1
    valid_product["supplier"] = sample_supplier(-0.5)

    def handler(_request):
        return create_json_response(valid_product)

    async with create_test_client(handler) as client:
        result = await client.get_product_details(1)

    assert result["unit_price"] == 0.0
    assert result["weight_kg"] == 1.0
    assert result["supplier"]["reliability_score"] == -0.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("limit", "offset"),
    [
        (0, 0),
        (101, 0),
        (True, 0),
        (20, -1),
        (20, True),
    ],
)
async def test_list_products_rejects_invalid_pagination(
    limit,
    offset,
):
    """Refuse une pagination invalide avant tout appel HTTP."""

    async with create_test_client(
        lambda _request: pytest.fail(
            "Aucun appel HTTP ne devait être effectué."
        )
    ) as client:
        with pytest.raises(InvalidClientParameterError):
            await client.list_products(
                limit=limit,
                offset=offset,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "product_id",
    [0, -1, True, "12", None],
)
async def test_get_product_rejects_invalid_identifier(product_id):
    """Refuse un identifiant produit invalide avant l'appel HTTP."""

    async with create_test_client(
        lambda _request: pytest.fail(
            "Aucun appel HTTP ne devait être effectué."
        )
    ) as client:
        with pytest.raises(InvalidClientParameterError):
            await client.get_product_details(product_id)


@pytest.mark.asyncio
async def test_get_product_transforms_404():
    """Transforme une réponse 404 en erreur de ressource."""

    def handler(_request):
        return httpx.Response(
            404,
            json={
                "error": "not_found",
                "message": "Product not found.",
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(ResourceNotFoundError):
            await client.get_product_details(999999)


@pytest.mark.asyncio
async def test_product_api_transforms_server_error():
    """Transforme une erreur HTTP du service externe."""

    def handler(_request):
        return httpx.Response(
            500,
            json={
                "error": "server_error",
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="code 500",
        ):
            await client.list_products()


@pytest.mark.asyncio
async def test_product_api_rejects_invalid_json():
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
            await client.list_products()


@pytest.mark.asyncio
async def test_product_api_rejects_invalid_root_structure():
    """Refuse une réponse JSON dont la racine n'est pas un objet."""

    def handler(_request):
        return httpx.Response(
            200,
            json=[sample_product()],
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="objet JSON",
        ):
            await client.list_products()


@pytest.mark.asyncio
async def test_product_page_rejects_invalid_structure():
    """Refuse une structure de pagination incorrecte."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "count": "1",
                "limit": 20,
                "offset": 0,
                "results": [sample_product()],
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="count",
        ):
            await client.list_products()


@pytest.mark.asyncio
async def test_product_page_rejects_mismatched_limit():
    """Refuse une limite différente de celle demandée."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "count": 1,
                "limit": 10,
                "offset": 40,
                "results": [sample_product()],
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="limit",
        ):
            await client.list_products(
                limit=20,
                offset=40,
            )


@pytest.mark.asyncio
async def test_product_page_rejects_mismatched_offset():
    """Refuse un décalage différent de celui demandé."""

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "count": 1,
                "limit": 20,
                "offset": 0,
                "results": [sample_product()],
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="offset",
        ):
            await client.list_products(
                limit=20,
                offset=40,
            )


@pytest.mark.asyncio
async def test_product_page_rejects_too_many_results():
    """Refuse une page contenant plus de résultats que sa limite."""

    products = [
        sample_product(product_id)
        for product_id in range(1, 22)
    ]

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "count": len(products),
                "limit": 20,
                "offset": 40,
                "results": products,
            },
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="plus de résultats",
        ):
            await client.list_products(
                limit=20,
                offset=40,
            )


@pytest.mark.asyncio
async def test_product_rejects_missing_required_field():
    """Refuse un produit auquel il manque un champ essentiel."""

    invalid_product = sample_product()
    invalid_product.pop("category")

    def handler(_request):
        return httpx.Response(
            200,
            json=invalid_product,
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="contrat attendu",
        ):
            await client.get_product_details(1)


@pytest.mark.asyncio
async def test_product_rejects_unexpected_identifier():
    """Refuse un produit différent de celui demandé."""

    def handler(_request):
        return httpx.Response(
            200,
            json=sample_product(product_id=99),
        )

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="identifiant différent",
        ):
            await client.get_product_details(12)


@pytest.mark.asyncio
async def test_product_api_transforms_timeout():
    """Transforme un dépassement du délai HTTP."""

    def handler(request):
        raise httpx.ReadTimeout(
            "Délai dépassé",
            request=request,
        )

    async with create_test_client(handler) as client:
        with pytest.raises(ExternalServiceTimeoutError):
            await client.list_products()


@pytest.mark.asyncio
async def test_product_api_transforms_network_error():
    """Transforme une erreur de connexion HTTP."""

    def handler(request):
        raise httpx.ConnectError(
            "Connexion impossible",
            request=request,
        )

    async with create_test_client(handler) as client:
        with pytest.raises(ExternalServiceUnavailableError):
            await client.list_products()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        (
            "brand",
            123,
        ),
        (
            "currency",
            "",
        ),
        (
            "tags",
            [
                "valide",
                42,
            ],
        ),
        (
            "updated_at",
            "date-invalide",
        ),
        (
            "supplier",
            {
                "id": "SUP-INCOMPLET",
            },
        ),
        pytest.param(
            "unit_price",
            "1.5",
            id="unit-price-numeric-string",
        ),
        pytest.param(
            "unit_price",
            True,
            id="unit-price-boolean",
        ),
        pytest.param(
            "unit_price",
            -0.01,
            id="unit-price-negative",
        ),
        pytest.param(
            "unit_price",
            float("nan"),
            id="unit-price-nan",
        ),
        pytest.param(
            "unit_price",
            float("inf"),
            id="unit-price-positive-infinity",
        ),
        pytest.param(
            "unit_price",
            float("-inf"),
            id="unit-price-negative-infinity",
        ),
        pytest.param(
            "weight_kg",
            "1.0",
            id="weight-numeric-string",
        ),
        pytest.param(
            "weight_kg",
            False,
            id="weight-boolean",
        ),
        pytest.param(
            "weight_kg",
            -0.01,
            id="weight-negative",
        ),
        pytest.param(
            "weight_kg",
            float("nan"),
            id="weight-nan",
        ),
        pytest.param(
            "weight_kg",
            float("inf"),
            id="weight-positive-infinity",
        ),
        pytest.param(
            "weight_kg",
            float("-inf"),
            id="weight-negative-infinity",
        ),
        pytest.param(
            "updated_at",
            1721822400,
            id="updated-at-numeric-timestamp",
        ),
        pytest.param(
            "supplier",
            sample_supplier("0.9"),
            id="reliability-numeric-string",
        ),
        pytest.param(
            "supplier",
            sample_supplier(True),
            id="reliability-boolean",
        ),
        pytest.param(
            "supplier",
            sample_supplier(float("nan")),
            id="reliability-nan",
        ),
        pytest.param(
            "supplier",
            sample_supplier(float("inf")),
            id="reliability-positive-infinity",
        ),
        pytest.param(
            "supplier",
            sample_supplier(float("-inf")),
            id="reliability-negative-infinity",
        ),
    ],
)
async def test_product_rejects_invalid_complete_contract(
    field_name,
    invalid_value,
):
    """Refuse un produit qui enfreint le contrat Pydantic complet."""

    invalid_product = sample_product()
    invalid_product[field_name] = invalid_value

    def handler(_request):
        return create_json_response(invalid_product)

    async with create_test_client(handler) as client:
        with pytest.raises(
            ExternalServiceResponseError,
            match="contrat attendu",
        ):
            await client.get_product_details(1)
