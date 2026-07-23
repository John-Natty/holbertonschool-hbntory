#!/usr/bin/env python3
"""Règles de validation du stock et des branches."""

from app.extensions import db
from app.models.branch import Branch


class StockError(ValueError):
    """Erreur de base commune à toutes les erreurs de stock."""


class StockValidationError(StockError):
    """Erreur levée quand une valeur de stock ou une branche est invalide."""


class StockOperationError(StockError):
    """Erreur levée quand l'enregistrement du stock échoue en base."""


def validate_quantity(quantity: int) -> int:
    """Retourne la quantité si c'est un entier positif ou nul."""

    # Rejette les booléens et tout ce qui n'est pas un entier.
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise StockValidationError("La quantité doit être un entier.")

    # Un niveau de stock ne peut jamais être négatif.
    if quantity < 0:
        raise StockValidationError(
            "La quantité ne peut pas être négative."
        )

    return quantity


def validate_amount(amount: int) -> int:
    """Retourne le montant si c'est un entier strictement positif."""

    # Rejette les booléens et tout ce qui n'est pas un entier.
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise StockValidationError("La quantité doit être un entier.")

    # Un ajout ou un retrait doit porter sur au moins une unité.
    if amount <= 0:
        raise StockValidationError(
            "La quantité doit être strictement positive."
        )

    return amount


def validate_branch(branch_id: int) -> Branch:
    """Retourne la branche si elle existe, sinon lève une erreur."""

    # Cherche la branche correspondante dans la base.
    branch = db.session.get(Branch, branch_id)

    # Refuse un identifiant qui ne correspond à aucune branche.
    if branch is None:
        raise StockValidationError(
            "La branche indiquée n'existe pas."
        )

    return branch
