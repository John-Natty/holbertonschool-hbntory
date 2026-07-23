#!/usr/bin/env python3
"""Tests du client de l'API Produit externe."""

from unittest.mock import Mock, patch

import pytest
import requests

from app.services import product_api


@pytest.fixture(autouse=True)
def product_api_url(monkeypatch):
    """Configure une fausse URL pour empêcher tout appel réel."""

    monkeypatch.setenv(
        "PRODUCT_API_BASE_URL",
        "http://product-api.test",
    )


def create_response(status_code=200, json_data=None):
    """Crée une fausse réponse HTTP."""

    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    response.json.return_value = json_data

    return response


@patch("app.services.product_api.requests.get")
def test_get_product_retourne_les_details(mock_get):
    """Retourne les informations détaillées d'un produit."""

    mock_get.return_value = create_response(
        json_data={
            "id": 1,
            "name": "Laptop",
            "unit_price": 999.99,
        }
    )

    product = product_api.get_product(1)

    assert product == {
        "id": 1,
        "name": "Laptop",
        "unit_price": 999.99,
    }

    mock_get.assert_called_once_with(
        "http://product-api.test/api/v1/products/1",
        params=None,
        timeout=5,
    )


@patch("app.services.product_api.requests.get")
def test_search_products_retourne_les_resultats(mock_get):
    """Retourne les produits correspondant à une recherche."""

    mock_get.return_value = create_response(
        json_data={
            "results": [
                {
                    "id": 1,
                    "name": "Laptop",
                },
                {
                    "id": 2,
                    "name": "Gaming Laptop",
                },
            ],
        }
    )

    results = product_api.search_products("laptop")

    assert len(results) == 2
    assert results[0]["id"] == 1

    mock_get.assert_called_once_with(
        "http://product-api.test/api/v1/products/search",
        params={
            "q": "laptop",
        },
        timeout=5,
    )


@patch("app.services.product_api.requests.get")
def test_list_products_retourne_une_page(mock_get):
    """Retourne une page de produits."""

    expected_data = {
        "results": [
            {
                "id": 1,
                "name": "Laptop",
            },
        ],
        "limit": 20,
        "offset": 0,
    }

    mock_get.return_value = create_response(
        json_data=expected_data,
    )

    result = product_api.list_products()

    assert result == expected_data

    mock_get.assert_called_once_with(
        "http://product-api.test/api/v1/products",
        params={
            "limit": 20,
            "offset": 0,
        },
        timeout=5,
    )


@patch("app.services.product_api.requests.get")
def test_get_product_inexistant_leve_une_erreur(mock_get):
    """Transforme une réponse 404 en ProductNotFoundError."""

    mock_get.return_value = create_response(
        status_code=404,
        json_data={
            "error": "Produit introuvable",
        },
    )

    with pytest.raises(
        product_api.ProductNotFoundError,
        match="Produit introuvable",
    ):
        product_api.get_product(999999)


@patch("app.services.product_api.requests.get")
def test_erreur_http_leve_product_api_error(mock_get):
    """Transforme une erreur HTTP en ProductApiError."""

    mock_get.return_value = create_response(
        status_code=500,
        json_data={
            "error": "Erreur serveur",
        },
    )

    with pytest.raises(
        product_api.ProductApiError,
        match="code 500",
    ):
        product_api.list_products()


@patch("app.services.product_api.requests.get")
def test_erreur_reseau_leve_product_api_error(mock_get):
    """Transforme une panne réseau en ProductApiError."""

    mock_get.side_effect = requests.ConnectionError(
        "Connexion impossible"
    )

    with pytest.raises(
        product_api.ProductApiError,
        match="injoignable",
    ):
        product_api.get_product(1)


@patch("app.services.product_api.requests.get")
def test_json_invalide_leve_product_api_error(mock_get):
    """Refuse une réponse contenant un JSON invalide."""

    response = create_response()
    response.json.side_effect = ValueError("JSON invalide")
    mock_get.return_value = response

    with pytest.raises(
        product_api.ProductApiError,
        match="JSON invalide",
    ):
        product_api.get_product(1)


@patch("app.services.product_api.requests.get")
def test_structure_json_invalide_leve_une_erreur(mock_get):
    """Refuse une réponse JSON qui n'est pas un objet."""

    mock_get.return_value = create_response(
        json_data=[
            {
                "id": 1,
            },
        ],
    )

    with pytest.raises(
        product_api.ProductApiError,
        match="structure",
    ):
        product_api.get_product(1)


@patch("app.services.product_api.requests.get")
def test_produit_sans_identifiant_leve_une_erreur(mock_get):
    """Refuse une réponse produit ne contenant aucun identifiant."""

    mock_get.return_value = create_response(
        json_data={
            "name": "Laptop",
        },
    )

    with pytest.raises(
        product_api.ProductApiError,
        match="aucun identifiant",
    ):
        product_api.get_product(1)


@patch("app.services.product_api.requests.get")
def test_resultats_de_recherche_invalides_levent_une_erreur(mock_get):
    """Refuse un champ results qui n'est pas une liste."""

    mock_get.return_value = create_response(
        json_data={
            "results": "Laptop",
        },
    )

    with pytest.raises(
        product_api.ProductApiError,
        match="liste de résultats",
    ):
        product_api.search_products("laptop")
