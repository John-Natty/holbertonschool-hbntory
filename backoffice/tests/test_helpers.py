"""Outils communs utilisés par les tests PostgreSQL."""

import os

from sqlalchemy import text

from app.extensions import db


TEST_DATABASE_NAME = "hbntory_test"


def get_test_database_url():
    """Retourne l'URL de la base PostgreSQL réservée aux tests."""
    database_url = os.getenv("TEST_DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "TEST_DATABASE_URL doit être définie pour lancer les tests."
        )

    return database_url


def clean_test_database():
    """Supprime les données de test sans supprimer les tables."""
    database_name = db.session.execute(
        text("SELECT current_database()")
    ).scalar_one()

    # Protection contre une suppression sur la mauvaise base.
    if database_name != TEST_DATABASE_NAME:
        raise RuntimeError(
            "Nettoyage refusé : la base connectée n'est pas "
            f"{TEST_DATABASE_NAME}."
        )

    db.session.execute(
        text(
            "TRUNCATE TABLE stocks, users, branches "
            "RESTART IDENTITY CASCADE"
        )
    )
    db.session.commit()
