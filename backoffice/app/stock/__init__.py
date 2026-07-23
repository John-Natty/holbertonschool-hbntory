"""Blueprint consacré à la gestion du stock d'une branche."""

from flask import Blueprint

# Toutes les routes de stock commencent par /branches.
stock_bp = Blueprint(
    "stock",
    __name__,
    url_prefix="/branches",
)

# Importe les routes après la création du blueprint
# afin d'éviter les imports circulaires.
from app.stock import routes  # noqa: E402, F401
