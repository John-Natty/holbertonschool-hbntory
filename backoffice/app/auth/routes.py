"""Routes de connexion et de déconnexion."""

from urllib.parse import urljoin, urlsplit

from flask import flash, redirect, render_template, request, url_for
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import func, select

from app.auth import auth_bp
from app.auth.forms import LoginForm
from app.extensions import db
from app.models import User


def is_safe_redirect_target(target):
    """Vérifie qu'une redirection reste sur le domaine du Backoffice."""
    # Refuse une destination absente.
    if not target:
        return False

    # Adresse actuellement utilisée pour accéder au Backoffice.
    current_url = urlsplit(request.host_url)

    # Transforme la destination en adresse complète.
    redirect_url = urlsplit(
        urljoin(request.host_url, target)
    )

    # Accepte uniquement les redirections HTTP ou HTTPS
    # qui restent sur le même domaine.
    return (
        redirect_url.scheme in {"http", "https"}
        and redirect_url.netloc == current_url.netloc
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Connecte un utilisateur avec son username et son mot de passe."""
    # Un utilisateur déjà connecté n'a pas besoin
    # de revoir le formulaire de connexion.
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    # Crée le formulaire Flask-WTF.
    form = LoginForm()

    # validate_on_submit vérifie :
    # - que la requête est en POST ;
    # - que les champs sont valides ;
    # - que le jeton CSRF est valide.
    if form.validate_on_submit():
        # Normalise le username comme lors de sa création.
        normalized_username = form.username.data.strip().lower()

        # Recherche le compte sans tenir compte des majuscules.
        user = db.session.scalar(
            select(User).where(
                func.lower(User.username) == normalized_username
            )
        )

        # Utilise un message générique pour ne pas révéler
        # si le username existe ou si le compte est désactivé.
        invalid_credentials = (
            user is None
            or not user.is_active
            or not user.check_password(form.password.data)
        )

        if invalid_credentials:
            flash(
                "Nom d'utilisateur ou mot de passe incorrect.",
                "danger",
            )
            return render_template(
                "auth/login.html",
                form=form,
            )

        # Crée la session Flask-Login.
        login_user(
            user,
            remember=form.remember.data,
        )

        flash(
            f"Bienvenue {user.username}.",
            "success",
        )

        # Flask-Login ajoute parfois une destination next
        # lorsqu'un utilisateur est redirigé vers la connexion.
        next_page = request.args.get("next")

        # Refuse une redirection vers un autre site.
        if not is_safe_redirect_target(next_page):
            next_page = url_for("main.dashboard")

        return redirect(next_page)

    # Affiche le formulaire pour une requête GET
    # ou lorsqu'une validation échoue.
    return render_template(
        "auth/login.html",
        form=form,
    )


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Déconnecte l'utilisateur actuellement authentifié."""
    # Supprime l'utilisateur de la session Flask-Login.
    logout_user()

    flash(
        "Vous êtes maintenant déconnecté.",
        "success",
    )

    return redirect(url_for("auth.login"))
