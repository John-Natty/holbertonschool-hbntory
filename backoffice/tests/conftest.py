#!/usr/bin/env python3
"""Fixtures et configuration partagées pour les tests du Backoffice."""

import os

import pytest

from app import create_app
from app.extensions import db
from app.models.branch import Branch
from tests.test_helpers import (
    clean_test_database,
    get_test_database_url,
)

# Empêche un test mal mocké de contacter la véritable API Produit.
os.environ.setdefault(
    "PRODUCT_API_BASE_URL",
    "http://product-api.invalid",
)

TEST_INTERNAL_API_KEY = (
    "cle-interne-reservee-aux-tests-hbntory"
)


@pytest.fixture
def app_context():
    """Crée une application reliée uniquement à hbntory_test."""

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": (
                "cle-secrete-reservee-aux-tests-hbntory"
            ),
            "INTERNAL_API_KEY": TEST_INTERNAL_API_KEY,
            "SQLALCHEMY_DATABASE_URI": get_test_database_url(),
        }
    )

    with app.app_context():
        # Vérifie current_database() puis nettoie avant le test.
        clean_test_database()

        try:
            yield app

        finally:
            # Répare une éventuelle transaction laissée en erreur.
            db.session.rollback()

            # Vérifie encore la base puis nettoie après le test.
            clean_test_database()
            db.session.remove()


@pytest.fixture
def client(app_context):
    """Retourne un client HTTP Flask pour les tests."""

    return app_context.test_client()


@pytest.fixture
def internal_api_headers():
    """Retourne l'en-tête valide de l'API interne."""

    return {
        "X-Internal-API-Key": TEST_INTERNAL_API_KEY,
    }


@pytest.fixture
def branch(app_context):
    """Crée une branche dans la base PostgreSQL de test."""

    test_branch = Branch(name="Branche de test pytest")
    db.session.add(test_branch)
    db.session.commit()

    return test_branch
