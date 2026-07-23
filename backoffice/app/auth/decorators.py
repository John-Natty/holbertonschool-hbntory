"""Décorateurs utilisés pour contrôler les autorisations."""

from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def admin_required(view_function):
    """Autorise uniquement les administrateurs."""
    @login_required
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        # Refuse l'accès si l'utilisateur n'est pas administrateur.
        if current_user.role != "admin":
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped_view


def common_required(view_function):
    """Autorise uniquement les utilisateurs communs avec une branche."""
    @login_required
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        # Un administrateur ne doit pas gérer les stocks.
        if current_user.role != "common":
            abort(403)

        # Un utilisateur commun doit obligatoirement avoir une branche.
        if current_user.branch_id is None:
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped_view


def own_branch_required(view_function):
    """Limite un utilisateur commun à sa propre branche."""
    @login_required
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        # Le décorateur doit être utilisé sur une route
        # possédant un paramètre nommé branch_id.
        requested_branch_id = kwargs.get("branch_id")

        if requested_branch_id is None:
            raise RuntimeError(
                "Le décorateur own_branch_required nécessite "
                "un paramètre de route nommé branch_id."
            )

        # Seuls les utilisateurs communs peuvent accéder aux stocks.
        if current_user.role != "common":
            abort(403)

        # Refuse un utilisateur commun sans branche.
        if current_user.branch_id is None:
            abort(403)

        # Refuse l'accès aux données d'une autre branche.
        if current_user.branch_id != requested_branch_id:
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped_view
