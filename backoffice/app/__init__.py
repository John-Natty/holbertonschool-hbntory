"""Initialisation de l'application Backoffice."""

import os

from flask import Flask
from sqlalchemy import select

from app.extensions import (
    bcrypt,
    csrf,
    db,
    login_manager,
    migrate,
)


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

    # Récupère les variables obligatoires.
    database_url = os.getenv("DATABASE_URL")
    secret_key = os.getenv("SECRET_KEY")

    # Refuse de démarrer sans connexion PostgreSQL.
    if not database_url:
        raise RuntimeError(
            "La variable d'environnement DATABASE_URL est manquante."
        )

    # Refuse de démarrer sans clé de session.
    if not secret_key:
        raise RuntimeError(
            "La variable d'environnement SECRET_KEY est manquante."
        )

    # Refuse la valeur factice du fichier d'exemple.
    if secret_key == "your_flask_secret_key":
        raise RuntimeError(
            "La variable SECRET_KEY utilise encore une valeur d'exemple."
        )

    # Configure SQLAlchemy.
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Configure la signature des sessions et des formulaires CSRF.
    app.config["SECRET_KEY"] = secret_key

    # Empêche JavaScript d'accéder au cookie de session.
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    # Limite l'envoi du cookie depuis des sites externes.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Doit être activé uniquement lorsque HTTPS est utilisé.
    app.config["SESSION_COOKIE_SECURE"] = env_to_bool(
        "SESSION_COOKIE_SECURE",
        default=False,
    )

    # Donne un nom identifiable au cookie de session.
    app.config["SESSION_COOKIE_NAME"] = "hbntory_session"

    # Initialise toutes les extensions Flask.
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Configure la route de connexion.
    login_manager.login_view = "auth.login"

    # Message affiché lors d'un accès anonyme
    # à une route protégée.
    login_manager.login_message = (
        "Vous devez vous connecter pour accéder à cette page."
    )
    login_manager.login_message_category = "warning"

    # Renforce la protection contre le vol de session.
    login_manager.session_protection = "strong"

    # Importe les modèles pour les enregistrer dans SQLAlchemy.
    from app import models

    @login_manager.user_loader
    def load_user(user_id):
        """Recharge un utilisateur actif depuis la session."""
        try:
            # L'identifiant stocké dans la session est une chaîne.
            numeric_user_id = int(user_id)

        except (TypeError, ValueError):
            # Refuse un identifiant invalide.
            return None

        # Recharge uniquement un utilisateur encore actif.
        return db.session.scalar(
            select(models.User).where(
                models.User.id == numeric_user_id,
                models.User.is_active.is_(True),
            )
        )

    # Importe les blueprints après l'initialisation des extensions.
    from app.auth import auth_bp
    from app.main import main_bp

    # Enregistre les routes d'authentification.
    app.register_blueprint(auth_bp)

    # Enregistre les routes principales.
    app.register_blueprint(main_bp)

    return app
