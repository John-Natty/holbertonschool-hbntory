"""Initialisation de l'API interne de consultation des stocks."""

from flask import Blueprint


internal_api_bp = Blueprint(
    "internal_api",
    __name__,
    url_prefix="/internal/stocks",
)


# Importe les routes après la création du blueprint.
from app.internal_api import routes  # noqa: E402, F401
