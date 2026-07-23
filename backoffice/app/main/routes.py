"""Routes principales du Backoffice."""

from flask import render_template
from flask_login import login_required

from app.main import main_bp


@main_bp.route("/")
@login_required
def dashboard():
    """Affiche la page d'accueil réservée aux utilisateurs connectés."""
    return render_template("dashboard.html")
