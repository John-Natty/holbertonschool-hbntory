#!/usr/bin/env python3
"""Tests des opérations de stock du common user (Task 3.1)."""

import pytest

from app.extensions import db
from app.models.stock import Stock
from app.services import stock_operations as ops
from app.services.stock_validation import (
    StockOperationError,
    StockValidationError,
)

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


def test_contrainte_violee_leve_une_stock_operation_error(branch):
    """Une contrainte refusée par la base lève StockOperationError."""

    # La contrainte ck_stocks_quantity_non_negative refuse cette ligne.
    db.session.add(
        Stock(
            branch_id=branch.id,
            product_id=PRODUCT_ID,
            quantity=-5,
        )
    )

    with pytest.raises(StockOperationError):
        ops._commit_or_fail()


def test_la_session_reste_utilisable_apres_un_echec(branch):
    """Après un échec, la session annulée accepte une nouvelle opération."""

    db.session.add(
        Stock(
            branch_id=branch.id,
            product_id=PRODUCT_ID,
            quantity=-5,
        )
    )

    with pytest.raises(StockOperationError):
        ops._commit_or_fail()

    # Sans le rollback, cet ajout échouerait à son tour.
    ops.add_stock(branch.id, PRODUCT_ID, 4)

    assert ops.get_stock_quantity(branch.id, PRODUCT_ID) == 4
