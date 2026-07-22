#!/usr/bin/env python3
"""Tests des opérations de stock du common user (Task 3.1)."""

import pytest

from app.services import stock_operations as ops
from app.services.stock_validation import StockValidationError

PRODUCT_ID = 1


def test_add_stock_cree_puis_incremente(branch):
    """Ajouter du stock crée la ligne puis incrémente la quantité."""

    ops.add_stock(branch.id, PRODUCT_ID, 10)
    assert ops.get_stock_quantity(branch.id, PRODUCT_ID) == 10
    ops.add_stock(branch.id, PRODUCT_ID, 5)
    assert ops.get_stock_quantity(branch.id, PRODUCT_ID) == 15


def test_remove_stock_decremente(branch):
    """Retirer du stock diminue la quantité disponible."""

    ops.add_stock(branch.id, PRODUCT_ID, 10)
    ops.remove_stock(branch.id, PRODUCT_ID, 4)
    assert ops.get_stock_quantity(branch.id, PRODUCT_ID) == 6


def test_remove_stock_refuse_trop_grand(branch):
    """Retirer plus que le stock disponible est refusé."""

    ops.add_stock(branch.id, PRODUCT_ID, 3)
    with pytest.raises(StockValidationError):
        ops.remove_stock(branch.id, PRODUCT_ID, 10)


def test_remove_stock_refuse_produit_absent(branch):
    """Retirer un produit absent du stock est refusé."""

    with pytest.raises(StockValidationError):
        ops.remove_stock(branch.id, PRODUCT_ID, 1)


def test_list_stock_retourne_les_lignes(branch):
    """Lister le stock renvoie les lignes de la branche."""

    ops.add_stock(branch.id, PRODUCT_ID, 8)
    lignes = ops.list_stock(branch.id)
    assert len(lignes) == 1
    assert lignes[0].quantity == 8


def test_get_quantity_produit_absent_vaut_zero(branch):
    """Consulter un produit absent renvoie une quantité de zéro."""

    assert ops.get_stock_quantity(branch.id, 999) == 0
