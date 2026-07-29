"""Routes de connexion et de déconnexion."""

from urllib.parse import unquote, urlsplit

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
    """Accepte uniquement un chemin interne au Backoffice."""
    # Refuse une destination absente ou d'un mauvais type.
    if not target or not isinstance(target, str):
        return False

    # Décode plusieurs fois pour repérer les caractères encodés.
    decoded_target = target

    for _ in range(3):
        new_target = unquote(decoded_target)

        if new_target == decoded_target:
            break

        decoded_target = new_target

    # Refuse les antislashs, souvent interprétés comme des slashs
    # par certains navigateurs.
    if "\\" in decoded_target:
        return False

    # Refuse les caractères de contrôle comme les retours à la ligne.
    if any(
        ord(character) < 32 or ord(character) == 127
        for character in decoded_target
    ):
        return False

    # La destination doit commencer par un seul slash.
    if (
        not decoded_target.startswith("/")
        or decoded_target.startswith("//")
    ):
        return False

    # Analyse la destination après son décodage.
    parsed_target = urlsplit(decoded_target)

    # Refuse toute destination contenant un domaine ou un protocole.
    return not parsed_target.scheme and not parsed_target.netloc


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Connecte un utilisateur avec son username et son mot de passe."""
    # Redirige un utilisateur déjà connecté vers le tableau de bord.
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    # Crée le formulaire de connexion protégé par CSRF.
    form = LoginForm()

    # Vérifie la méthode POST, les champs et le jeton CSRF.
    if form.validate_on_submit():
        # Normalise le nom d'utilisateur avant la recherche.
        normalized_username = form.username.data.strip().lower()

        # Recherche le compte sans tenir compte de la casse.
        user = db.session.scalar(
            select(User).where(
                func.lower(User.username) == normalized_username
            )
        )

        # Refuse un compte absent, inactif ou un mot de passe incorrect.
        invalid_credentials = (
            user is None
            or not user.is_active
            or not user.check_password(form.password.data)
        )

        if invalid_credentials:
            # Utilise un message générique pour éviter
            # de révéler l'existence d'un compte.
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

        # Récupère la destination demandée avant la connexion.
        next_page = request.args.get("next")

        # Utilise le tableau de bord si la destination est dangereuse.
        if not is_safe_redirect_target(next_page):
            next_page = url_for("main.dashboard")

        return redirect(next_page)

    # Affiche le formulaire pour une requête GET
    # ou lorsque sa validation échoue.
    return render_template(
        "auth/login.html",
        form=form,
    )


@auth_bp.route("/entree")
def entree():
    """Entrée publique du Backoffice, toujours sur une session vierge.

    Le site public y renvoie. Sur un poste partagé en branche, l'employé
    suivant ne doit jamais hériter de la session du précédent : la
    session en cours est donc fermée avant d'afficher le formulaire.
    """

    if current_user.is_authenticated:
        logout_user()

        flash(
            "La session précédente a été fermée.",
            "info",
        )

    return redirect(url_for("auth.login"))


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
