#!/usr/bin/env python3
"""Tests du client de l'API Produit (Task 3.3)."""

import pytest

from app.services import product_api


def test_get_product_retourne_les_details():
    """Un produit existant renvoie ses informations détaillées."""

    produit = product_api.get_product(1)
    assert produit["id"] == 1
    assert "name" in produit
    assert "unit_price" in produit


def test_search_products_trouve_des_resultats():
    """La recherche renvoie au moins un résultat pour un mot-clé courant."""

    resultats = product_api.search_products("laptop")
    assert len(resultats) > 0


def test_get_product_inexistant_leve_une_erreur():
    """Un identifiant inexistant lève ProductNotFoundError."""

    with pytest.raises(product_api.ProductNotFoundError):
        product_api.get_product(999999)
