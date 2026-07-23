#!/usr/bin/env python3
"""Services de lecture utilisés par l'API interne des stocks."""

from collections import defaultdict

from sqlalchemy import select

from app.extensions import db
from app.models.branch import Branch
from app.models.stock import Stock
from app.services.stock_validation import (
    StockValidationError,
    validate_amount,
    validate_branch,
)


class InternalAPIValidationError(ValueError):
    """Erreur levée quand une requête interne est invalide."""


def get_stock_by_product(product_id: int) -> list[dict]:
    """Retourne les branches possédant un produit en stock."""

    _validate_positive_identifier(product_id, "product_id")

    rows = db.session.execute(
        select(
            Branch.id,
            Branch.name,
            Stock.quantity,
        )
        .join(Stock, Stock.branch_id == Branch.id)
        .where(
            Stock.product_id == product_id,
            Stock.quantity > 0,
        )
        .order_by(Branch.id)
    ).all()

    return [
        {
            "branch_id": branch_id,
            "branch_name": branch_name,
            "quantity": quantity,
        }
        for branch_id, branch_name, quantity in rows
    ]


def get_stock_by_branch(branch_id: int) -> tuple[Branch, list[dict]]:
    """Retourne les produits disponibles dans une branche."""

    _validate_positive_identifier(branch_id, "branch_id")

    # Lève StockValidationError si la branche n'existe pas.
    branch = validate_branch(branch_id)

    stocks = db.session.scalars(
        select(Stock)
        .where(
            Stock.branch_id == branch_id,
            Stock.quantity > 0,
        )
        .order_by(Stock.product_id)
    ).all()

    return branch, [
        {
            "product_id": stock.product_id,
            "quantity": stock.quantity,
        }
        for stock in stocks
    ]


def check_shopping_list(items: list[dict]) -> list[dict]:
    """Retourne les branches pouvant satisfaire toute la liste."""

    requested_items = _normalize_items(items)
    product_ids = list(requested_items)

    rows = db.session.execute(
        select(
            Branch.id,
            Branch.name,
            Stock.product_id,
            Stock.quantity,
        )
        .join(Stock, Stock.branch_id == Branch.id)
        .where(
            Stock.product_id.in_(product_ids),
            Stock.quantity > 0,
        )
        .order_by(Branch.id, Stock.product_id)
    ).all()

    branch_names = {}
    available_by_branch = defaultdict(dict)

    for branch_id, branch_name, product_id, quantity in rows:
        branch_names[branch_id] = branch_name
        available_by_branch[branch_id][product_id] = quantity

    matching_branches = []

    for branch_id in sorted(available_by_branch):
        available_items = available_by_branch[branch_id]

        # Une branche doit satisfaire chaque produit demandé.
        if not all(
            available_items.get(product_id, 0) >= requested_quantity
            for product_id, requested_quantity
            in requested_items.items()
        ):
            continue

        matching_branches.append(
            {
                "branch_id": branch_id,
                "branch_name": branch_names[branch_id],
                "items": [
                    {
                        "product_id": product_id,
                        "requested_quantity": requested_quantity,
                        "available_quantity": available_items[
                            product_id
                        ],
                    }
                    for product_id, requested_quantity
                    in requested_items.items()
                ],
            }
        )

    return matching_branches


def _normalize_items(items: list[dict]) -> dict[int, int]:
    """Valide et regroupe les produits identiques d'une liste."""

    if not isinstance(items, list) or not items:
        raise InternalAPIValidationError(
            "Le champ items doit être une liste non vide."
        )

    normalized_items = {}

    for item in items:
        if not isinstance(item, dict):
            raise InternalAPIValidationError(
                "Chaque élément de items doit être un objet JSON."
            )

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        _validate_positive_identifier(product_id, "product_id")

        try:
            validate_amount(quantity)

        except StockValidationError as error:
            raise InternalAPIValidationError(str(error)) from error

        # Additionne les quantités si un produit apparaît plusieurs fois.
        normalized_items[product_id] = (
            normalized_items.get(product_id, 0) + quantity
        )

    return dict(sorted(normalized_items.items()))


def _validate_positive_identifier(value: int, field_name: str) -> int:
    """Valide un identifiant entier strictement positif."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise InternalAPIValidationError(
            f"Le champ {field_name} doit être un entier."
        )

    if value <= 0:
        raise InternalAPIValidationError(
            f"Le champ {field_name} doit être strictement positif."
        )

    return value
