"""Blueprint consacré à l'authentification."""

from flask import Blueprint

# Toutes les routes du blueprint commenceront par /auth.
auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
)

# Importe les routes après la création du blueprint
# pour éviter les imports circulaires.
from app.auth import routes  # noqa: E402, F401
