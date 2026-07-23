#!/usr/bin/env python3
"""Routes de l'API interne de consultation des stocks."""

from flask import current_app, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.internal_api import internal_api_bp
from app.internal_api.decorators import internal_api_key_required
from app.internal_api.services import (
    InternalAPIValidationError,
    check_shopping_list,
    get_stock_by_branch,
    get_stock_by_product,
)
from app.services.stock_validation import StockValidationError


@internal_api_bp.get("/products/<product_id>")
@internal_api_key_required
def stock_by_product(product_id):
    """Retourne les branches possédant un produit en stock."""

    try:
        numeric_product_id = _parse_identifier(
            product_id,
            "product_id",
        )

        branches = get_stock_by_product(numeric_product_id)

    except InternalAPIValidationError as error:
        return _error_response(
            "invalid_identifier",
            str(error),
            400,
        )

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Impossible de consulter le stock par produit."
        )

        return _error_response(
            "internal_error",
            "Une erreur interne empêche la consultation du stock.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "product_id": numeric_product_id,
            "branches": branches,
            "error": None,
        }
    ), 200


@internal_api_bp.get("/branches/<branch_id>")
@internal_api_key_required
def stock_by_branch(branch_id):
    """Retourne les produits disponibles dans une branche."""

    try:
        numeric_branch_id = _parse_identifier(
            branch_id,
            "branch_id",
        )

        branch, stocks = get_stock_by_branch(numeric_branch_id)

    except InternalAPIValidationError as error:
        return _error_response(
            "invalid_identifier",
            str(error),
            400,
        )

    except StockValidationError:
        return _error_response(
            "branch_not_found",
            "La branche demandée n'existe pas.",
            404,
        )

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Impossible de consulter le stock par branche."
        )

        return _error_response(
            "internal_error",
            "Une erreur interne empêche la consultation du stock.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "branch": {
                "id": branch.id,
                "name": branch.name,
            },
            "stocks": stocks,
            "error": None,
        }
    ), 200


@internal_api_bp.post("/check-shopping-list")
@internal_api_key_required
def shopping_list():
    """Retourne les branches pouvant satisfaire une liste d'achats."""

    try:
        payload = request.get_json(silent=True)

        if not isinstance(payload, dict):
            raise InternalAPIValidationError(
                "Le corps de la requête doit être un objet JSON."
            )

        matching_branches = check_shopping_list(
            payload.get("items")
        )

    except InternalAPIValidationError as error:
        return _error_response(
            "invalid_request",
            str(error),
            400,
        )

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Impossible de vérifier la liste d'achats."
        )

        return _error_response(
            "internal_error",
            "Une erreur interne empêche la vérification de la liste.",
            500,
        )

    return jsonify(
        {
            "success": True,
            "matching_branches": matching_branches,
            "error": None,
        }
    ), 200


def _parse_identifier(raw_value, field_name):
    """Convertit un identifiant provenant de l'URL en entier."""

    try:
        return int(raw_value)

    except (TypeError, ValueError) as error:
        raise InternalAPIValidationError(
            f"Le champ {field_name} doit être un entier."
        ) from error


def _error_response(code, message, status_code):
    """Construit une réponse d'erreur JSON homogène."""

    return jsonify(
        {
            "success": False,
            "error": {
                "code": code,
                "message": message,
            },
        }
    ), status_code
