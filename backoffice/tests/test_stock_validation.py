#!/usr/bin/env python3
"""Tests des règles de validation du stock (Task 1.4)."""

import pytest

from app.services.stock_validation import (
    StockValidationError,
    validate_amount,
    validate_quantity,
)


def test_validate_quantity_accepte_zero_et_positif():
    """Une quantité entière positive ou nulle est acceptée."""

    assert validate_quantity(0) == 0
    assert validate_quantity(7) == 7


def test_validate_quantity_refuse_negatif():
    """Une quantité négative est refusée."""

    with pytest.raises(StockValidationError):
        validate_quantity(-1)


def test_validate_quantity_refuse_non_entier():
    """Une valeur non entière (texte ou booléen) est refusée."""

    with pytest.raises(StockValidationError):
        validate_quantity("abc")
    with pytest.raises(StockValidationError):
        validate_quantity(True)


def test_validate_amount_accepte_positif():
    """Un montant entier strictement positif est accepté."""

    assert validate_amount(3) == 3


def test_validate_amount_refuse_zero_et_negatif():
    """Un montant nul ou négatif est refusé."""

    with pytest.raises(StockValidationError):
        validate_amount(0)
    with pytest.raises(StockValidationError):
        validate_amount(-5)
