#!/usr/bin/env python3
"""Fixtures et configuration partagées pour les tests du Backoffice."""

import os

import pytest

from app import create_app
from app.extensions import db
from app.models.branch import Branch
from app.models.stock import Stock

# Valeurs par défaut pour lancer les tests en local (base et API Docker).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://hbntory_user:your_database_password@localhost:5432/hbntory",
)
os.environ.setdefault("PRODUCT_API_BASE_URL", "http://localhost:5001")


@pytest.fixture
def app_context():
    """Ouvre un contexte d'application Flask relié à la base."""

    app = create_app()
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
