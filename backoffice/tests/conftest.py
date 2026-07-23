#!/usr/bin/env python3
"""Fixtures et configuration partagées pour les tests du Backoffice."""

import os

import pytest

from app import create_app
from app.extensions import db
from app.models.branch import Branch
from app.models.stock import Stock
from tests.test_helpers import get_test_database_url

# Valeurs par défaut pour lancer les tests en local (base et API Docker).
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql://hbntory_user:your_database_password"
    "@localhost:5432/hbntory_test",
)
os.environ.setdefault("PRODUCT_API_BASE_URL", "http://localhost:5001")


@pytest.fixture
def app_context():
    """Ouvre un contexte d'application Flask relié à la base de test."""

    # La configuration de test reprend celle des tests de sécurité.
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "cle-secrete-reservee-aux-tests-hbntory",
            "SQLALCHEMY_DATABASE_URI": get_test_database_url(),
        }
    )

    with app.app_context():
        yield


@pytest.fixture
def branch(app_context):
    """Crée une branche de test et nettoie tout à la fin."""

    test_branch = Branch(name="Branche de test pytest")
    db.session.add(test_branch)
    db.session.commit()

    yield test_branch

    # Supprime d'abord les stocks liés, puis la branche elle-même.
    db.session.query(Stock).filter_by(branch_id=test_branch.id).delete()
    db.session.delete(test_branch)
    db.session.commit()
