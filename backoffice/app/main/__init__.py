"""Blueprint des pages principales du Backoffice."""

from flask import Blueprint

# Blueprint principal du Backoffice.
main_bp = Blueprint(
    "main",
    __name__,
)

# Importe les routes après la création du blueprint.
from app.main import routes  # noqa: E402, F401
