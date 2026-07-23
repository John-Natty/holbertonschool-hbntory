"""Décorateurs de sécurité utilisés par l'API interne."""

from functools import wraps
from hmac import compare_digest

from flask import current_app, jsonify, request


def internal_api_key_required(view_function):
    """Refuse les requêtes ne possédant pas la bonne clé interne."""

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        """Vérifie la clé avant d'exécuter la route protégée."""

        # Clé configurée dans l'environnement du Backoffice.
        expected_key = current_app.config.get("INTERNAL_API_KEY")

        # Clé transmise par le serveur MCP.
        provided_key = request.headers.get("X-Internal-API-Key")

        # La configuration sera également contrôlée au démarrage.
        if not expected_key:
            raise RuntimeError(
                "La variable INTERNAL_API_KEY n'est pas configurée."
            )

        # Refuse une clé absente ou différente.
        if (
            not provided_key
            or not compare_digest(provided_key, expected_key)
        ):
            return jsonify(
                {
                    "success": False,
                    "error": {
                        "code": "forbidden",
                        "message": (
                            "Clé interne absente ou incorrecte."
                        ),
                    },
                }
            ), 403

        return view_function(*args, **kwargs)

    return wrapped_view
