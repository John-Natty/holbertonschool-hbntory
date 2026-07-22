"""Blueprint consacré à l'administration du Backoffice."""

from flask import Blueprint

# Toutes les routes d'administration commencent par /admin.
admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
)

# Importe les routes après la création du blueprint
# afin d'éviter les imports circulaires.
from app.admin import routes  # noqa: E402, F401
