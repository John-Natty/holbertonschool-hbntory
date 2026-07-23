"""Initialisation de l'application Backoffice."""

import os

from flask import Flask, render_template
from sqlalchemy import select

from app.extensions import (
    bcrypt,
    csrf,
    db,
    login_manager,
    migrate,
)

# Valeurs d'exemple qui ne doivent jamais être utilisées réellement.
PLACEHOLDER_SECRET_KEYS = {
    "your_flask_secret_key",
    "replace_with_a_random_secret",
}


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


def create_app(test_config=None):
    """Crée et configure l'application Flask."""
    # Crée l'instance principale de l'application.
    app = Flask(__name__)

    # Charge la configuration normale depuis l'environnement.
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.getenv("SECRET_KEY"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=env_to_bool(
            "SESSION_COOKIE_SECURE",
            default=False,
        ),
        SESSION_COOKIE_NAME="hbntory_session",
    )

    # Remplace la configuration normale pendant les tests.
    if test_config is not None:
        app.config.update(test_config)

    # Récupère les valeurs finales après la configuration de test.
    database_url = app.config.get("SQLALCHEMY_DATABASE_URI")
    secret_key = app.config.get("SECRET_KEY")

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

    # Refuse une clé qui n'est pas une chaîne de caractères.
    if not isinstance(secret_key, str):
        raise RuntimeError(
            "La variable SECRET_KEY doit être une chaîne."
        )

    # Refuse les valeurs factices présentes dans les exemples.
    if secret_key in PLACEHOLDER_SECRET_KEYS:
        raise RuntimeError(
            "La variable SECRET_KEY utilise encore une valeur d'exemple."
        )

    # Refuse une clé trop courte.
    if len(secret_key) < 32:
        raise RuntimeError(
            "La variable SECRET_KEY doit contenir "
            "au moins 32 caractères."
        )

    # Sécurise le cookie créé par l'option « Rester connecté ».
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"

    # Le cookie remember utilise la même règle HTTPS
    # que le cookie principal de session.
    app.config["REMEMBER_COOKIE_SECURE"] = app.config[
        "SESSION_COOKIE_SECURE"
    ]

    # Initialise les extensions Flask.
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Configure la route de connexion.
    login_manager.login_view = "auth.login"

    # Message affiché lorsqu'un visiteur anonyme
    # tente d'accéder à une route protégée.
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
            # Flask-Login stocke l'identifiant sous forme de chaîne.
            numeric_user_id = int(user_id)

        except (TypeError, ValueError):
            # Refuse un identifiant de session invalide.
            return None

        # Recharge uniquement un utilisateur encore actif.
        return db.session.scalar(
            select(models.User).where(
                models.User.id == numeric_user_id,
                models.User.is_active.is_(True),
            )
        )

    # Importe les blueprints après les extensions.
    from app.auth import auth_bp
    from app.main import main_bp
    from app.admin import admin_bp

    # Enregistre les routes d'authentification.
    app.register_blueprint(auth_bp)

    # Enregistre les routes principales.
    app.register_blueprint(main_bp)

    # Enregistre les routes d'administration.
    app.register_blueprint(admin_bp)

    @app.errorhandler(403)
    def forbidden(_error):
        """Affiche une page personnalisée lors d'un accès interdit."""
        return render_template("errors/403.html"), 403

    return app
