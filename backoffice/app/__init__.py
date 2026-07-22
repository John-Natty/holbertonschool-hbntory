"""Initialisation de l'application Backoffice."""

import os

from flask import Flask
from sqlalchemy import select

from app.extensions import bcrypt, db, login_manager, migrate


def env_to_bool(variable_name, default=False):
    """Convertit une variable d'environnement en booléen."""
    # Récupère la valeur présente dans l'environnement.
    value = os.getenv(variable_name)

    # Retourne la valeur par défaut si la variable est absente.
    if value is None:
        return default

    # Accepte plusieurs écritures courantes représentant vrai.
    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def create_app():
    """Crée et configure l'application Flask."""
    # Crée l'instance principale de l'application.
    app = Flask(__name__)

    # Récupère l'adresse de connexion à PostgreSQL.
    database_url = os.getenv("DATABASE_URL")

    # Récupère la clé utilisée pour signer les sessions Flask.
    secret_key = os.getenv("SECRET_KEY")

    # Empêche le démarrage sans connexion à la base de données.
    if not database_url:
        raise RuntimeError(
            "La variable d'environnement DATABASE_URL est manquante."
        )

    # Empêche le démarrage sans clé de session.
    if not secret_key:
        raise RuntimeError(
            "La variable d'environnement SECRET_KEY est manquante."
        )

    # Refuse la valeur factice présente dans le fichier d'exemple.
    if secret_key == "your_flask_secret_key":
        raise RuntimeError(
            "La variable SECRET_KEY utilise encore une valeur d'exemple."
        )

    # Configure la connexion SQLAlchemy.
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Configure la clé utilisée pour signer les cookies de session.
    app.config["SECRET_KEY"] = secret_key

    # Empêche JavaScript d'accéder au cookie de session.
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    # Réduit les risques d'envoi du cookie depuis un autre site.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Active ce réglage uniquement lorsque l'application utilise HTTPS.
    app.config["SESSION_COOKIE_SECURE"] = env_to_bool(
        "SESSION_COOKIE_SECURE",
        default=False,
    )

    # Donne un nom propre au cookie de session.
    app.config["SESSION_COOKIE_NAME"] = "hbntory_session"

    # Initialise les extensions Flask.
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Configure la route vers laquelle un visiteur anonyme sera envoyé.
    login_manager.login_view = "auth.login"

    # Message affiché lorsqu'une page nécessite une authentification.
    login_manager.login_message = (
        "Vous devez vous connecter pour accéder à cette page."
    )

    # Catégorie utilisée par les messages flash.
    login_manager.login_message_category = "warning"

    # Renforce la protection de la session en cas de changement suspect.
    login_manager.session_protection = "strong"

    # Importe tous les modèles afin que SQLAlchemy les connaisse.
    from app import models

    @login_manager.user_loader
    def load_user(user_id):
        """Recharge un utilisateur depuis son identifiant de session."""
        try:
            # Flask-Login stocke l'identifiant sous forme de chaîne.
            numeric_user_id = int(user_id)

        except (TypeError, ValueError):
            # Refuse un identifiant de session invalide.
            return None

        # Recherche uniquement un utilisateur actif.
        return db.session.scalar(
            select(models.User).where(
                models.User.id == numeric_user_id,
                models.User.is_active.is_(True),
            )
        )

    return app
