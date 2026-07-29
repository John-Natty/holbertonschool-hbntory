#!/usr/bin/env python3
"""Tests des routes de gestion du stock d'une branche."""

from unittest.mock import Mock

import pytest

from app import create_app
from app.extensions import db
from app.models import Branch, User
from app.services import stock_operations as ops
from tests.test_helpers import clean_test_database, get_test_database_url

PRODUCT_ID = 1
COMMON_PASSWORD = "MotDePasseCommun123!"
ADMIN_PASSWORD = "MotDePasseAdmin123!"


@pytest.fixture
def stock_app(monkeypatch):
    """Prépare une application de test avec deux branches et deux comptes."""

    def fake_get_product(product_id):
        """Retourne un produit stable ou simule une référence inconnue."""

        if product_id == 999999:
            from app.services.product_api import ProductNotFoundError

            raise ProductNotFoundError("Produit introuvable.")

        return {
            "id": product_id,
            "name": f"Produit {product_id}",
            "category": "Tests",
            "unit_price": 19.99,
            "currency": "EUR",
        }

    def fake_list_products(limit=20, offset=0):
        """Retourne un catalogue déterministe sans appel réseau."""

        products = [fake_get_product(PRODUCT_ID)]
        return {
            "count": len(products),
            "limit": limit,
            "offset": offset,
            "results": products[offset:offset + limit],
        }

    monkeypatch.setattr(
        "app.stock.routes.product_api.get_product",
        fake_get_product,
    )
    monkeypatch.setattr(
        "app.stock.routes.product_api.list_products",
        fake_list_products,
    )

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "cle-secrete-reservee-aux-tests-hbntory",
            "SQLALCHEMY_DATABASE_URI": get_test_database_url(),
            "SESSION_COOKIE_SECURE": False,
            "WTF_CSRF_ENABLED": False,
        }
    )

    with app.app_context():
        clean_test_database()

        toulouse = Branch(name="Toulouse")
        carcassonne = Branch(name="Carcassonne")
        db.session.add_all([toulouse, carcassonne])
        db.session.flush()

        employe = User(
            username="employe",
            role="common",
            is_active=True,
            branch_id=toulouse.id,
        )
        employe.set_password(COMMON_PASSWORD)

        admin = User(
            username="admin",
            role="admin",
            is_active=True,
            branch_id=None,
        )
        admin.set_password(ADMIN_PASSWORD)

        db.session.add_all([employe, admin])
        db.session.commit()

        app.config["TOULOUSE_ID"] = toulouse.id
        app.config["CARCASSONNE_ID"] = carcassonne.id

        yield app


@pytest.fixture
def client(stock_app):
    """Retourne un client HTTP simulant un navigateur."""

    return stock_app.test_client()


def login(client, username, password):
    """Connecte un utilisateur au Backoffice."""

    return client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def test_visiteur_anonyme_redirige_vers_connexion(stock_app, client):
    """Un visiteur non connecté est renvoyé vers la page de connexion."""

    reponse = client.get(
        f"/branches/{stock_app.config['TOULOUSE_ID']}/stock"
    )

    assert reponse.status_code == 302
    assert "/auth/login" in reponse.headers["Location"]


def test_common_user_voit_le_stock_de_sa_branche(stock_app, client):
    """Un common user accède au stock de sa propre branche."""

    with stock_app.app_context():
        ops.add_stock(stock_app.config["TOULOUSE_ID"], PRODUCT_ID, 7)

    login(client, "employe", COMMON_PASSWORD)

    reponse = client.get(
        f"/branches/{stock_app.config['TOULOUSE_ID']}/stock"
    )

    assert reponse.status_code == 200
    assert "7" in reponse.get_data(as_text=True)


def test_common_user_refuse_sur_une_autre_branche(stock_app, client):
    """Un common user ne peut pas consulter le stock d'une autre branche."""

    login(client, "employe", COMMON_PASSWORD)

    reponse = client.get(
        f"/branches/{stock_app.config['CARCASSONNE_ID']}/stock"
    )

    assert reponse.status_code == 403


@pytest.mark.parametrize("action", ["add", "remove"])
def test_common_user_ne_modifie_pas_une_autre_branche(
    stock_app,
    client,
    monkeypatch,
    action,
):
    """Refuse les opérations POST sur le stock d'une autre branche."""

    branch_id = stock_app.config["CARCASSONNE_ID"]

    with stock_app.app_context():
        ops.add_stock(branch_id, PRODUCT_ID, 10)

    product_lookup = Mock(
        return_value={
            "id": PRODUCT_ID,
            "name": "Produit de test",
        }
    )
    monkeypatch.setattr(
        "app.stock.routes.product_api.get_product",
        product_lookup,
    )
    login(client, "employe", COMMON_PASSWORD)

    reponse = client.post(
        f"/branches/{branch_id}/stock/{action}",
        data={
            "product_id": PRODUCT_ID,
            "amount": 1,
        },
    )

    assert reponse.status_code == 403
    product_lookup.assert_not_called()

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 10


def test_admin_refuse_sur_le_stock(stock_app, client):
    """Un administrateur n'a pas le droit de gérer le stock."""

    login(client, "admin", ADMIN_PASSWORD)

    reponse = client.get(
        f"/branches/{stock_app.config['TOULOUSE_ID']}/stock"
    )

    assert reponse.status_code == 403


@pytest.mark.parametrize("action", ["add", "remove"])
def test_admin_ne_modifie_pas_le_stock(
    stock_app,
    client,
    monkeypatch,
    action,
):
    """Refuse directement les opérations POST de stock à l'admin."""

    branch_id = stock_app.config["TOULOUSE_ID"]

    with stock_app.app_context():
        ops.add_stock(branch_id, PRODUCT_ID, 10)

    product_lookup = Mock(
        return_value={
            "id": PRODUCT_ID,
            "name": "Produit de test",
        }
    )
    monkeypatch.setattr(
        "app.stock.routes.product_api.get_product",
        product_lookup,
    )
    login(client, "admin", ADMIN_PASSWORD)

    reponse = client.post(
        f"/branches/{branch_id}/stock/{action}",
        data={
            "product_id": PRODUCT_ID,
            "amount": 1,
        },
    )

    assert reponse.status_code == 403
    product_lookup.assert_not_called()

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 10


def test_ajout_de_stock(stock_app, client, monkeypatch):
    """Un common user ajoute une quantité au stock de sa branche."""

    monkeypatch.setattr(
        "app.stock.routes.product_api.get_product",
        Mock(
            return_value={
                "id": PRODUCT_ID,
                "name": "Produit de test",
            }
        ),
    )
    login(client, "employe", COMMON_PASSWORD)
    branch_id = stock_app.config["TOULOUSE_ID"]

    reponse = client.post(
        f"/branches/{branch_id}/stock/add",
        data={"product_id": PRODUCT_ID, "amount": 5},
        follow_redirects=True,
    )

    assert reponse.status_code == 200

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 5


def test_retrait_de_stock(stock_app, client):
    """Un common user retire une quantité du stock de sa branche."""

    branch_id = stock_app.config["TOULOUSE_ID"]

    with stock_app.app_context():
        ops.add_stock(branch_id, PRODUCT_ID, 10)

    login(client, "employe", COMMON_PASSWORD)

    client.post(
        f"/branches/{branch_id}/stock/remove",
        data={"product_id": PRODUCT_ID, "amount": 4},
        follow_redirects=True,
    )

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 6


def test_retrait_trop_grand_affiche_une_erreur(stock_app, client):
    """Retirer plus que le stock disponible affiche un message d'erreur."""

    branch_id = stock_app.config["TOULOUSE_ID"]

    with stock_app.app_context():
        ops.add_stock(branch_id, PRODUCT_ID, 2)

    login(client, "employe", COMMON_PASSWORD)

    reponse = client.post(
        f"/branches/{branch_id}/stock/remove",
        data={"product_id": PRODUCT_ID, "amount": 50},
        follow_redirects=True,
    )

    assert "insuffisante" in reponse.get_data(as_text=True).lower()

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 2


def test_ajout_refuse_un_produit_inexistant(stock_app, client):
    """Ajouter un produit inconnu de l'API Produit est refusé."""

    login(client, "employe", COMMON_PASSWORD)
    branch_id = stock_app.config["TOULOUSE_ID"]

    reponse = client.post(
        f"/branches/{branch_id}/stock/add",
        data={"product_id": 999999, "amount": 3},
        follow_redirects=True,
    )

    assert "Aucun produit" in reponse.get_data(as_text=True)

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, 999999) == 0


def test_le_common_user_arrive_sur_le_stock_de_sa_branche(stock_app, client):
    """Le common user atterrit directement sur le stock de sa branche."""

    reponse = login(client, "employe", COMMON_PASSWORD)
    page = reponse.get_data(as_text=True)

    # Le menu ne propose plus de lien « Stock » : la page d'accueil EST
    # le stock de la branche, le lien ferait doublon.
    assert "Stock de Toulouse" in page
    assert f"/branches/{stock_app.config['TOULOUSE_ID']}/stock" in page


def test_le_menu_cache_le_lien_stock_a_l_admin(stock_app, client):
    """Le menu ne propose aucun lien vers le stock pour un administrateur."""

    reponse = login(client, "admin", ADMIN_PASSWORD)

    assert "/stock" not in reponse.get_data(as_text=True)


def test_quantite_negative_refusee(stock_app, client):
    """Une quantité nulle ou négative est refusée par le formulaire."""

    login(client, "employe", COMMON_PASSWORD)
    branch_id = stock_app.config["TOULOUSE_ID"]

    reponse = client.post(
        f"/branches/{branch_id}/stock/add",
        data={"product_id": PRODUCT_ID, "amount": -3},
        follow_redirects=True,
    )

    assert "strictement positive" in reponse.get_data(as_text=True)

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 0
