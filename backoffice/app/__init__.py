"""Initialisation de l'application Backoffice."""

import os

from flask import Flask

from app.extensions import bcrypt, db, migrate


def create_app():
    """Crée et configure l'application Flask."""
    app = Flask(__name__)

    # Récupère l'adresse de PostgreSQL depuis l'environnement.
    database_url = os.getenv("DATABASE_URL")

    # Arrête clairement le démarrage si la variable est absente.
    if not database_url:
        raise RuntimeError(
            "La variable d'environnement DATABASE_URL est manquante."
        )

    # Configure la connexion à PostgreSQL.
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url

    # Désactive le système de suivi devenu inutile.
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialise les extensions Flask.
    db.init_app(app)
    bcrypt.init_app(app)

    # Importe les modèles pour les enregistrer dans les métadonnées.
    from app import models  # noqa: F401

    # Relie Flask-Migrate à l'application et à SQLAlchemy.
    migrate.init_app(app, db)

    return app
