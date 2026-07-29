"""Routes principales du Backoffice."""

from flask import render_template
from flask_login import current_user, login_required

from app.admin.routes import render_users_page
from app.main import main_bp
from app.stock.routes import render_stock_page


@main_bp.route("/")
@login_required
def dashboard():
    """Affiche la page d'accueil correspondant au rôle de l'utilisateur."""

    # L'administrateur gère les comptes : il arrive directement dessus.
    if current_user.role == "admin":
        return render_users_page()

    # Un employé arrive directement sur le stock de sa branche.
    if current_user.branch_id is not None:
        return render_stock_page(current_user.branch_id)

    # Compte commun sans branche : il n'a aucun stock à gérer.
    return render_template("dashboard.html")
