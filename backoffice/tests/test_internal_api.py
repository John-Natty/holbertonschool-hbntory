#!/usr/bin/env python3
"""Tests de l'API interne de consultation des stocks."""

from app.extensions import db
from app.models.branch import Branch
from app.models.stock import Stock


def create_stock(branch, product_id, quantity):
    """Crée une ligne de stock pour les besoins d'un test."""

    stock = Stock(
        branch_id=branch.id,
        product_id=product_id,
        quantity=quantity,
    )
    db.session.add(stock)
    db.session.commit()

    return stock


def test_request_without_internal_key_is_forbidden(client):
    """Refuse une requête ne contenant aucune clé interne."""

    response = client.get("/internal/stocks/products/12")

    assert response.status_code == 403
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "forbidden",
            "message": "Clé interne absente ou incorrecte.",
        },
    }


def test_request_with_invalid_internal_key_is_forbidden(client):
    """Refuse une requête contenant une mauvaise clé interne."""

    response = client.get(
        "/internal/stocks/products/12",
        headers={
            "X-Internal-API-Key": "mauvaise-cle",
        },
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_stock_by_product_returns_matching_branches(
    client,
    internal_api_headers,
    app_context,
):
    """Retourne les branches possédant le produit demandé."""

    toulouse = Branch(name="Toulouse")
    carcassonne = Branch(name="Carcassonne")
    db.session.add_all([toulouse, carcassonne])
    db.session.commit()

    create_stock(toulouse, product_id=12, quantity=8)
    create_stock(carcassonne, product_id=12, quantity=3)
    create_stock(toulouse, product_id=25, quantity=4)

    response = client.get(
        "/internal/stocks/products/12",
        headers=internal_api_headers,
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "product_id": 12,
        "branches": [
            {
                "branch_id": toulouse.id,
                "branch_name": "Toulouse",
                "quantity": 8,
            },
            {
                "branch_id": carcassonne.id,
                "branch_name": "Carcassonne",
                "quantity": 3,
            },
        ],
        "error": None,
    }


def test_stock_by_product_returns_empty_list(
    client,
    internal_api_headers,
):
    """Retourne une liste vide quand le produit est absent."""

    response = client.get(
        "/internal/stocks/products/999",
        headers=internal_api_headers,
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "product_id": 999,
        "branches": [],
        "error": None,
    }


def test_stock_by_product_rejects_invalid_identifier(
    client,
    internal_api_headers,
):
    """Refuse un identifiant produit invalide."""

    response = client.get(
        "/internal/stocks/products/invalid",
        headers=internal_api_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == (
        "invalid_identifier"
    )


def test_stock_by_product_rejects_non_positive_identifier(
    client,
    internal_api_headers,
):
    """Refuse un identifiant produit nul ou négatif."""

    response = client.get(
        "/internal/stocks/products/0",
        headers=internal_api_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == (
        "invalid_identifier"
    )


def test_stock_by_branch_returns_available_products(
    client,
    internal_api_headers,
    branch,
):
    """Retourne les produits disponibles dans une branche."""

    create_stock(branch, product_id=25, quantity=4)
    create_stock(branch, product_id=12, quantity=8)

    response = client.get(
        f"/internal/stocks/branches/{branch.id}",
        headers=internal_api_headers,
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "branch": {
            "id": branch.id,
            "name": branch.name,
        },
        "stocks": [
            {
                "product_id": 12,
                "quantity": 8,
            },
            {
                "product_id": 25,
                "quantity": 4,
            },
        ],
        "error": None,
    }


def test_stock_by_branch_returns_empty_list(
    client,
    internal_api_headers,
    branch,
):
    """Retourne une liste vide quand la branche n'a aucun stock."""

    response = client.get(
        f"/internal/stocks/branches/{branch.id}",
        headers=internal_api_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["stocks"] == []


def test_stock_by_branch_returns_not_found(
    client,
    internal_api_headers,
):
    """Retourne 404 lorsque la branche n'existe pas."""

    response = client.get(
        "/internal/stocks/branches/999999",
        headers=internal_api_headers,
    )

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "branch_not_found",
            "message": "La branche demandée n'existe pas.",
        },
    }


def test_stock_by_branch_name_requires_internal_key(client):
    """Protège aussi la résolution par nom avec la clé interne."""

    response = client.get(
        "/internal/stocks/branches/by-name",
        query_string={"name": "Toulouse"},
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_stock_by_branch_name_is_case_insensitive_and_normalizes_spaces(
    client,
    internal_api_headers,
    branch,
):
    """Résout le même nom quelle que soit la casse ou les espaces."""

    create_stock(branch, product_id=12, quantity=8)

    for branch_name in (
        branch.name,
        branch.name.lower(),
        branch.name.upper(),
        f"  {branch.name}  ",
    ):
        response = client.get(
            "/internal/stocks/branches/by-name",
            query_string={"name": branch_name},
            headers=internal_api_headers,
        )

        assert response.status_code == 200
        assert response.get_json() == {
            "success": True,
            "branch": {
                "id": branch.id,
                "name": branch.name,
            },
            "stocks": [
                {
                    "product_id": 12,
                    "quantity": 8,
                },
            ],
            "error": None,
        }


def test_stock_by_branch_name_returns_structured_not_found(
    client,
    internal_api_headers,
):
    """Retourne une erreur métier lorsque le nom est inconnu."""

    response = client.get(
        "/internal/stocks/branches/by-name",
        query_string={"name": "Inconnue"},
        headers=internal_api_headers,
    )

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "branch_not_found",
            "message": "La branche demandée n'existe pas.",
        },
    }


def test_stock_by_branch_name_rejects_empty_name(
    client,
    internal_api_headers,
):
    """Refuse un nom manquant ou vide."""

    response = client.get(
        "/internal/stocks/branches/by-name",
        query_string={"name": "   "},
        headers=internal_api_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == (
        "invalid_branch_name"
    )


def test_stock_by_branch_name_rejects_ambiguous_normalized_match(
    client,
    internal_api_headers,
    app_context,
):
    """Ne choisit jamais arbitrairement entre deux noms normalisés."""

    db.session.add_all(
        [
            Branch(name="Toulouse"),
            Branch(name="  Toulouse  "),
        ]
    )
    db.session.commit()

    response = client.get(
        "/internal/stocks/branches/by-name",
        query_string={"name": "toulouse"},
        headers=internal_api_headers,
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == (
        "ambiguous_branch"
    )


def test_shopping_list_returns_matching_branches(
    client,
    internal_api_headers,
    app_context,
):
    """Retourne les branches pouvant satisfaire toute la liste."""

    toulouse = Branch(name="Toulouse")
    carcassonne = Branch(name="Carcassonne")
    db.session.add_all([toulouse, carcassonne])
    db.session.commit()

    create_stock(toulouse, product_id=12, quantity=8)
    create_stock(toulouse, product_id=25, quantity=4)
    create_stock(carcassonne, product_id=12, quantity=10)
    create_stock(carcassonne, product_id=25, quantity=1)

    response = client.post(
        "/internal/stocks/check-shopping-list",
        headers=internal_api_headers,
        json={
            "items": [
                {
                    "product_id": 12,
                    "quantity": 3,
                },
                {
                    "product_id": 25,
                    "quantity": 2,
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "matching_branches": [
            {
                "branch_id": toulouse.id,
                "branch_name": "Toulouse",
                "items": [
                    {
                        "product_id": 12,
                        "requested_quantity": 3,
                        "available_quantity": 8,
                    },
                    {
                        "product_id": 25,
                        "requested_quantity": 2,
                        "available_quantity": 4,
                    },
                ],
            },
        ],
        "error": None,
    }


def test_shopping_list_returns_empty_list(
    client,
    internal_api_headers,
    branch,
):
    """Retourne une liste vide si aucune branche ne convient."""

    create_stock(branch, product_id=12, quantity=1)

    response = client.post(
        "/internal/stocks/check-shopping-list",
        headers=internal_api_headers,
        json={
            "items": [
                {
                    "product_id": 12,
                    "quantity": 5,
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.get_json()["matching_branches"] == []


def test_shopping_list_groups_duplicate_products(
    client,
    internal_api_headers,
    branch,
):
    """Additionne les quantités d'un même produit demandé plusieurs fois."""

    create_stock(branch, product_id=12, quantity=8)

    response = client.post(
        "/internal/stocks/check-shopping-list",
        headers=internal_api_headers,
        json={
            "items": [
                {
                    "product_id": 12,
                    "quantity": 3,
                },
                {
                    "product_id": 12,
                    "quantity": 2,
                },
            ],
        },
    )

    assert response.status_code == 200

    matching_branch = response.get_json()["matching_branches"][0]
    item = matching_branch["items"][0]

    assert item["product_id"] == 12
    assert item["requested_quantity"] == 5
    assert item["available_quantity"] == 8


def test_shopping_list_rejects_missing_json_body(
    client,
    internal_api_headers,
):
    """Refuse une requête sans corps JSON."""

    response = client.post(
        "/internal/stocks/check-shopping-list",
        headers=internal_api_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_request"


def test_shopping_list_rejects_empty_items(
    client,
    internal_api_headers,
):
    """Refuse une liste d'achats vide."""

    response = client.post(
        "/internal/stocks/check-shopping-list",
        headers=internal_api_headers,
        json={
            "items": [],
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_request"


def test_shopping_list_rejects_invalid_quantity(
    client,
    internal_api_headers,
):
    """Refuse une quantité nulle, négative ou non entière."""

    response = client.post(
        "/internal/stocks/check-shopping-list",
        headers=internal_api_headers,
        json={
            "items": [
                {
                    "product_id": 12,
                    "quantity": 0,
                },
            ],
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_request"


def test_shopping_list_does_not_require_csrf_token(
    client,
    internal_api_headers,
):
    """Autorise le serveur MCP à utiliser la route sans jeton CSRF."""

    response = client.post(
        "/internal/stocks/check-shopping-list",
        headers=internal_api_headers,
        json={
            "items": [
                {
                    "product_id": 12,
                    "quantity": 1,
                },
            ],
        },
    )

    assert response.status_code == 200


def test_internal_api_key_configuration_is_validated():
    """Refuse les configurations dangereuses de la clé interne."""

    import pytest

    from app import create_app

    invalid_keys = [
        (
            None,
            "INTERNAL_API_KEY est manquante",
        ),
        (
            12345,
            "INTERNAL_API_KEY doit être une chaîne",
        ),
        (
            "cle-trop-courte",
            "au moins 32 caractères",
        ),
        (
            "your_private_internal_api_key",
            "utilise encore une valeur d'exemple",
        ),
    ]

    for internal_api_key, expected_message in invalid_keys:
        with pytest.raises(
            RuntimeError,
            match=expected_message,
        ):
            create_app(
                {
                    "TESTING": True,
                    "SECRET_KEY": (
                        "cle-secrete-reservee-aux-tests-hbntory"
                    ),
                    "INTERNAL_API_KEY": internal_api_key,
                    "SQLALCHEMY_DATABASE_URI": (
                        "postgresql://user:password@localhost/test"
                    ),
                }
            )


def test_unknown_internal_route_returns_json(
    client,
    internal_api_headers,
):
    """Retourne une erreur JSON pour une route interne inconnue."""

    response = client.get(
        "/internal/stocks/route-inconnue",
        headers=internal_api_headers,
    )

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "not_found",
            "message": (
                "La ressource interne demandée n'existe pas."
            ),
        },
    }


def test_invalid_internal_method_returns_json(
    client,
    internal_api_headers,
):
    """Retourne une erreur JSON pour une méthode interdite."""

    response = client.post(
        "/internal/stocks/products/12",
        headers=internal_api_headers,
    )

    assert response.status_code == 405
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "method_not_allowed",
            "message": (
                "Cette méthode HTTP n'est pas autorisée."
            ),
        },
    }


def test_unexpected_internal_error_returns_json(
    app_context,
    client,
    internal_api_headers,
):
    """Transforme une erreur interne inattendue en JSON."""

    @app_context.get("/internal/stocks/test-error")
    def internal_test_error():
        """Lève volontairement une erreur pour le test."""

        raise RuntimeError("Erreur volontaire")

    # Flask propage normalement les exceptions en mode TESTING.
    app_context.config["PROPAGATE_EXCEPTIONS"] = False

    response = client.get(
        "/internal/stocks/test-error",
        headers=internal_api_headers,
    )

    assert response.status_code == 500
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "internal_error",
            "message": (
                "Une erreur interne empêche de traiter la requête."
            ),
        },
    }
