#!/usr/bin/env python3
"""Opérations de stock disponibles pour un common user."""

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.stock import Stock
from app.services.stock_validation import (
    StockOperationError,
    StockValidationError,
    validate_amount,
    validate_branch,
)


def list_stock(branch_id: int) -> list[Stock]:
    """Retourne toutes les lignes de stock d'une branche."""

    # Vérifie que la branche existe avant de lister.
    validate_branch(branch_id)

    # Récupère les lignes de stock de la branche, triées par produit.
    return (
        db.session.query(Stock)
        .filter_by(branch_id=branch_id)
        .order_by(Stock.product_id)
        .all()
    )


def get_stock_quantity(branch_id: int, product_id: int) -> int:
    """Retourne la quantité d'un produit dans une branche."""

    # Vérifie que la branche existe.
    validate_branch(branch_id)

    # Cherche la ligne de stock correspondante.
    stock = _find_stock(branch_id, product_id)

    # Une ligne absente signifie simplement une quantité nulle.
    if stock is None:
        return 0

    return stock.quantity


def add_stock(branch_id: int, product_id: int, amount: int) -> Stock:
    """Ajoute une quantité au stock d'un produit dans une branche."""

    # Valide la branche et la quantité ajoutée.
    validate_branch(branch_id)
    validate_amount(amount)

    # Récupère la ligne existante, s'il y en a une.
    stock = _find_stock(branch_id, product_id)

    if stock is None:
        # Première entrée de ce produit dans cette branche.
        stock = Stock(
            branch_id=branch_id,
            product_id=product_id,
            quantity=amount,
        )
        db.session.add(stock)
    else:
        # Incrémente le stock déjà présent.
        stock.quantity += amount

    _commit_or_fail()

    return stock


def remove_stock(branch_id: int, product_id: int, amount: int) -> Stock:
    """Retire atomiquement une quantité disponible dans une branche."""

    # Valide la branche et la quantité retirée.
    validate_branch(branch_id)
    validate_amount(amount)

    # PostgreSQL décide dans une seule instruction si le retrait est possible.
    # La condition est réévaluée après l'attente d'un éventuel verrou concurrent.
    statement = (
        update(Stock)
        .where(
            Stock.branch_id == branch_id,
            Stock.product_id == product_id,
            Stock.quantity >= amount,
        )
        .values(quantity=Stock.quantity - amount)
        .returning(Stock)
    )

    try:
        stock = db.session.execute(statement).scalar_one_or_none()

    except SQLAlchemyError as error:
        db.session.rollback()

        raise StockOperationError(
            "L'enregistrement du stock a échoué."
        ) from error

    if stock is None:
        # Distingue un produit absent d'une quantité devenue insuffisante.
        existing_stock = _find_stock(branch_id, product_id)
        db.session.rollback()

        if existing_stock is None:
            raise StockValidationError(
                "Ce produit n'est pas en stock dans cette branche."
            )

        raise StockValidationError(
            "Quantité insuffisante en stock."
        )

    _commit_or_fail()

    return stock


def _find_stock(branch_id: int, product_id: int) -> Stock | None:
    """Retourne la ligne de stock d'un produit dans une branche, ou None."""

    return (
        db.session.query(Stock)
        .filter_by(branch_id=branch_id, product_id=product_id)
        .first()
    )


def _commit_or_fail() -> None:
    """Enregistre la transaction en cours, ou l'annule si elle échoue."""

    try:
        db.session.commit()

    except IntegrityError as error:
        # Une contrainte de la base a refusé l'enregistrement.
        db.session.rollback()

        raise StockOperationError(
            "Le stock vient d'être modifié par une autre opération. "
            "Merci de réessayer."
        ) from error

    except SQLAlchemyError as error:
        # Toute autre panne laisserait la session inutilisable.
        db.session.rollback()

        raise StockOperationError(
            "L'enregistrement du stock a échoué."
        ) from error
