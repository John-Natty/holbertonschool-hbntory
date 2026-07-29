#!/usr/bin/env python3
"""Tests de l'entrée publique du Backoffice, sur session vierge."""

from tests.test_stock_routes import (  # noqa: F401
    COMMON_PASSWORD,
    client,
    login,
    stock_app,
)


def test_visiteur_anonyme_arrive_sur_la_connexion(stock_app, client):
    """Sans session, l'entrée mène simplement au formulaire."""

    reponse = client.get("/auth/entree")

    assert reponse.status_code == 302
    assert "/auth/login" in reponse.headers["Location"]


def test_l_entree_ferme_la_session_en_cours(stock_app, client):
    """Un employé déjà identifié repart d'une session vierge."""

    login(client, "employe", COMMON_PASSWORD)

    # La session est bien active avant de passer par l'entrée.
    assert client.get("/").status_code == 200

    reponse = client.get("/auth/entree", follow_redirects=True)
    page = reponse.get_data(as_text=True)

    assert reponse.status_code == 200
    assert "Connexion" in page
    assert "La session précédente a été fermée." in page


def test_apres_l_entree_l_accueil_redemande_une_connexion(
    stock_app,
    client,
):
    """La session est réellement fermée, pas seulement masquée."""

    login(client, "employe", COMMON_PASSWORD)
    client.get("/auth/entree")

    reponse = client.get("/", follow_redirects=False)

    assert reponse.status_code == 302
    assert "/auth/login" in reponse.headers["Location"]
