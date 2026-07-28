#!/usr/bin/env python3
"""Tests de la route JSON de mouvement de stock utilisée par les cartes."""

import re
from html import unescape

from app.services import stock_operations as ops

# Réutilise les fixtures de la page de stock : mêmes branches, mêmes comptes.
from tests.test_stock_routes import (  # noqa: F401
    ADMIN_PASSWORD,
    COMMON_PASSWORD,
    PRODUCT_ID,
    client,
    login,
    stock_app,
)


def move(client, branch_id, payload):
    """Envoie un mouvement de stock au format attendu par le navigateur."""

    return client.post(
        f"/branches/{branch_id}/stock/move",
        json=payload,
    )


def test_mouvement_positif_ajoute_au_stock(stock_app, client):
    """Un montant positif crée la ligne de stock et retourne le total."""

    login(client, "employe", COMMON_PASSWORD)
    branch_id = stock_app.config["TOULOUSE_ID"]

    reponse = move(
        client,
        branch_id,
        {"product_id": PRODUCT_ID, "amount": 5},
    )

    assert reponse.status_code == 200
    assert reponse.get_json() == {"success": True, "quantity": 5}

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 5


def test_mouvement_negatif_retire_du_stock(stock_app, client):
    """Un montant négatif retire la quantité correspondante."""

    branch_id = stock_app.config["TOULOUSE_ID"]

    with stock_app.app_context():
        ops.add_stock(branch_id, PRODUCT_ID, 8)

    login(client, "employe", COMMON_PASSWORD)

    reponse = move(
        client,
        branch_id,
        {"product_id": PRODUCT_ID, "amount": -3},
    )

    assert reponse.status_code == 200
    assert reponse.get_json()["quantity"] == 5

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 5


def test_retrait_trop_grand_renvoie_la_quantite_reelle(stock_app, client):
    """Un retrait excessif est refusé et renvoie la quantité en base."""

    branch_id = stock_app.config["TOULOUSE_ID"]

    with stock_app.app_context():
        ops.add_stock(branch_id, PRODUCT_ID, 2)

    login(client, "employe", COMMON_PASSWORD)

    reponse = move(
        client,
        branch_id,
        {"product_id": PRODUCT_ID, "amount": -10},
    )

    donnees = reponse.get_json()

    assert reponse.status_code == 409
    assert donnees["success"] is False
    # La carte doit pouvoir se recaler sur la vraie valeur.
    assert donnees["quantity"] == 2

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 2


def test_mouvement_nul_refuse(stock_app, client):
    """Un mouvement de zéro n'a aucun sens et est rejeté."""

    login(client, "employe", COMMON_PASSWORD)

    reponse = move(
        client,
        stock_app.config["TOULOUSE_ID"],
        {"product_id": PRODUCT_ID, "amount": 0},
    )

    assert reponse.status_code == 400
    assert reponse.get_json()["success"] is False


def test_booleen_refuse_comme_quantite(stock_app, client):
    """« true » vaut 1 en Python : il doit être refusé explicitement."""

    login(client, "employe", COMMON_PASSWORD)
    branch_id = stock_app.config["TOULOUSE_ID"]

    reponse = move(
        client,
        branch_id,
        {"product_id": PRODUCT_ID, "amount": True},
    )

    assert reponse.status_code == 400

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 0


def test_champs_manquants_refuses(stock_app, client):
    """Une requête incomplète est rejetée sans toucher au stock."""

    login(client, "employe", COMMON_PASSWORD)

    reponse = move(
        client,
        stock_app.config["TOULOUSE_ID"],
        {"amount": 3},
    )

    assert reponse.status_code == 400


def test_produit_inconnu_refuse(stock_app, client):
    """Un identifiant absent de l'API Produit ne peut pas entrer en stock."""

    login(client, "employe", COMMON_PASSWORD)
    branch_id = stock_app.config["TOULOUSE_ID"]

    reponse = move(
        client,
        branch_id,
        {"product_id": 999999, "amount": 1},
    )

    assert reponse.status_code == 404

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, 999999) == 0


def test_mouvement_refuse_sur_une_autre_branche(stock_app, client):
    """Un employé ne peut pas modifier le stock d'une autre branche."""

    login(client, "employe", COMMON_PASSWORD)
    branch_id = stock_app.config["CARCASSONNE_ID"]

    reponse = move(
        client,
        branch_id,
        {"product_id": PRODUCT_ID, "amount": 4},
    )

    assert reponse.status_code == 403

    with stock_app.app_context():
        assert ops.get_stock_quantity(branch_id, PRODUCT_ID) == 0


def test_admin_refuse_sur_le_mouvement(stock_app, client):
    """Un administrateur n'a pas le droit de bouger du stock."""

    login(client, "admin", ADMIN_PASSWORD)
    branch_id = stock_app.config["TOULOUSE_ID"]

    reponse = move(
        client,
        branch_id,
        {"product_id": PRODUCT_ID, "amount": 4},
    )

    assert reponse.status_code == 403


def test_visiteur_anonyme_refuse_sur_le_mouvement(stock_app, client):
    """Un visiteur non connecté ne peut pas bouger du stock."""

    reponse = move(
        client,
        stock_app.config["TOULOUSE_ID"],
        {"product_id": PRODUCT_ID, "amount": 1},
    )

    assert reponse.status_code in (302, 401)


def test_mouvement_exige_un_jeton_csrf_valide(stock_app, client):
    """Protège réellement la route JSON lorsque CSRF est activé."""

    login(client, "employe", COMMON_PASSWORD)
    branch_id = stock_app.config["TOULOUSE_ID"]
    stock_app.config["WTF_CSRF_ENABLED"] = True

    page = client.get(f"/branches/{branch_id}/stock")
    match = re.search(
        r'data-csrf-token="([^"]+)"',
        page.get_data(as_text=True),
    )

    assert page.status_code == 200
    assert match is not None
    csrf_token = unescape(match.group(1))

    refused = move(
        client,
        branch_id,
        {"product_id": PRODUCT_ID, "amount": 1},
    )
    assert refused.status_code == 400

    accepted = client.post(
        f"/branches/{branch_id}/stock/move",
        json={"product_id": PRODUCT_ID, "amount": 1},
        headers={"X-CSRFToken": csrf_token},
    )
    assert accepted.status_code == 200
    assert accepted.get_json() == {
        "success": True,
        "quantity": 1,
    }
