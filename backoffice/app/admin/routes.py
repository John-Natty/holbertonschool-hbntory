"""Routes utilisées pour administrer les utilisateurs."""

from flask import abort, flash, redirect, render_template, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.admin import admin_bp
from app.admin.forms import CreateUserForm, EditUserForm
from app.auth.decorators import admin_required
from app.extensions import db
from app.models import Branch, User


def get_branches():
    """Retourne toutes les branches classées par nom."""
    # Classe les branches sans tenir compte des majuscules.
    return db.session.scalars(
        select(Branch).order_by(
            func.lower(Branch.name)
        )
    ).all()


def get_branch_choices():
    """Retourne les branches au format attendu par SelectField."""
    # Chaque choix contient l'identifiant et le nom de la branche.
    return [
        (branch.id, branch.name)
        for branch in get_branches()
    ]


def username_already_used(username, ignored_user_id=None):
    """Vérifie si un username est déjà utilisé."""
    # Normalise le username comme le fait le modèle User.
    normalized_username = username.strip().lower()

    # Recherche le username sans tenir compte de la casse.
    statement = select(User.id).where(
        func.lower(User.username) == normalized_username
    )

    # Lors d'une modification, ignore le compte actuellement édité.
    if ignored_user_id is not None:
        statement = statement.where(
            User.id != ignored_user_id
        )

    return db.session.scalar(statement) is not None


def get_common_user_or_404(user_id):
    """Retourne un utilisateur common ou déclenche une erreur 404."""
    # Recherche uniquement un compte possédant le rôle common.
    user = db.session.scalar(
        select(User).where(
            User.id == user_id,
            User.role == "common",
        )
    )

    # Empêche ces routes de gérer un compte administrateur.
    if user is None:
        abort(404)

    return user


@admin_bp.route("/users")
@admin_required
def list_users():
    """Affiche la liste des utilisateurs common."""
    # Charge les utilisateurs et leur branche efficacement.
    users = db.session.scalars(
        select(User)
        .options(selectinload(User.branch))
        .where(User.role == "common")
        .order_by(func.lower(User.username))
    ).all()

    return render_template(
        "admin/users.html",
        users=users,
    )


@admin_bp.route(
    "/users/create",
    methods=["GET", "POST"],
)
@admin_required
def create_user():
    """Crée un nouvel utilisateur common."""
    # Crée le formulaire.
    form = CreateUserForm()

    # Fournit les choix avant la validation du formulaire.
    form.branch_id.choices = get_branch_choices()

    # Empêche la création lorsqu'aucune branche n'existe.
    if not form.branch_id.choices:
        flash(
            "Aucune branche n'est disponible pour créer un utilisateur.",
            "warning",
        )

        return render_template(
            "admin/user_form.html",
            form=form,
            page_title="Créer un utilisateur",
            is_edit=False,
            branches_available=False,
        )

    # Vérifie les champs et le jeton CSRF.
    if form.validate_on_submit():
        # Normalise le username reçu.
        normalized_username = form.username.data.strip().lower()

        # Refuse un username déjà présent.
        if username_already_used(normalized_username):
            form.username.errors.append(
                "Ce nom d'utilisateur est déjà utilisé."
            )

            return render_template(
                "admin/user_form.html",
                form=form,
                page_title="Créer un utilisateur",
                is_edit=False,
                branches_available=True,
            )

        # Vérifie que la branche existe réellement.
        branch = db.session.get(
            Branch,
            form.branch_id.data,
        )

        if branch is None:
            form.branch_id.errors.append(
                "La branche sélectionnée n'existe pas."
            )

            return render_template(
                "admin/user_form.html",
                form=form,
                page_title="Créer un utilisateur",
                is_edit=False,
                branches_available=True,
            )

        # Le rôle est imposé côté serveur.
        user = User(
            username=normalized_username,
            role="common",
            is_active=True,
            branch_id=branch.id,
        )

        # Enregistre uniquement le hash bcrypt.
        user.set_password(form.password.data)

        db.session.add(user)

        try:
            # Enregistre définitivement le nouvel utilisateur.
            db.session.commit()

        except IntegrityError:
            # Annule la transaction en cas de username concurrent.
            db.session.rollback()

            form.username.errors.append(
                "Ce nom d'utilisateur est déjà utilisé."
            )

            return render_template(
                "admin/user_form.html",
                form=form,
                page_title="Créer un utilisateur",
                is_edit=False,
                branches_available=True,
            )

        except SQLAlchemyError:
            # Annule les changements en cas d'erreur SQL.
            db.session.rollback()

            flash(
                "Une erreur est survenue pendant la création.",
                "danger",
            )

            return render_template(
                "admin/user_form.html",
                form=form,
                page_title="Créer un utilisateur",
                is_edit=False,
                branches_available=True,
            )

        flash(
            f"L'utilisateur {user.username} a été créé.",
            "success",
        )

        return redirect(
            url_for("admin.list_users")
        )

    return render_template(
        "admin/user_form.html",
        form=form,
        page_title="Créer un utilisateur",
        is_edit=False,
        branches_available=True,
    )


@admin_bp.route(
    "/users/<int:user_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def edit_user(user_id):
    """Modifie un utilisateur common."""
    # Refuse un identifiant absent ou appartenant à un admin.
    user = get_common_user_or_404(user_id)

    # Préremplit le formulaire avec les données actuelles.
    form = EditUserForm(obj=user)

    # Fournit les branches disponibles avant la validation.
    form.branch_id.choices = get_branch_choices()

    if form.validate_on_submit():
        # Normalise le nouveau username.
        normalized_username = form.username.data.strip().lower()

        # Refuse un username appartenant à un autre compte.
        if username_already_used(
            normalized_username,
            ignored_user_id=user.id,
        ):
            form.username.errors.append(
                "Ce nom d'utilisateur est déjà utilisé."
            )

            return render_template(
                "admin/user_form.html",
                form=form,
                page_title="Modifier un utilisateur",
                is_edit=True,
                branches_available=True,
                user=user,
            )

        # Vérifie que la nouvelle branche existe.
        branch = db.session.get(
            Branch,
            form.branch_id.data,
        )

        if branch is None:
            form.branch_id.errors.append(
                "La branche sélectionnée n'existe pas."
            )

            return render_template(
                "admin/user_form.html",
                form=form,
                page_title="Modifier un utilisateur",
                is_edit=True,
                branches_available=True,
                user=user,
            )

        # Modifie uniquement les champs autorisés.
        user.username = normalized_username
        user.branch_id = branch.id

        # Conserve le mot de passe actuel si le champ reste vide.
        if (
            form.password.data
            and form.password.data.strip()
        ):
            user.set_password(form.password.data)

        try:
            # Enregistre les modifications.
            db.session.commit()

        except IntegrityError:
            db.session.rollback()

            form.username.errors.append(
                "Ce nom d'utilisateur est déjà utilisé."
            )

            return render_template(
                "admin/user_form.html",
                form=form,
                page_title="Modifier un utilisateur",
                is_edit=True,
                branches_available=True,
                user=user,
            )

        except SQLAlchemyError:
            db.session.rollback()

            flash(
                "Une erreur est survenue pendant la modification.",
                "danger",
            )

            return render_template(
                "admin/user_form.html",
                form=form,
                page_title="Modifier un utilisateur",
                is_edit=True,
                branches_available=True,
                user=user,
            )

        flash(
            f"L'utilisateur {user.username} a été modifié.",
            "success",
        )

        return redirect(
            url_for("admin.list_users")
        )

    return render_template(
        "admin/user_form.html",
        form=form,
        page_title="Modifier un utilisateur",
        is_edit=True,
        branches_available=True,
        user=user,
    )


@admin_bp.route(
    "/users/<int:user_id>/status",
    methods=["POST"],
)
@admin_required
def toggle_user_status(user_id):
    """Active ou désactive un utilisateur common."""
    # Empêche la modification d'un administrateur.
    user = get_common_user_or_404(user_id)

    # Inverse l'état actuel sans supprimer le compte.
    user.is_active = not user.is_active

    try:
        # Enregistre le nouveau statut.
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        flash(
            "Impossible de modifier l'état de cet utilisateur.",
            "danger",
        )

        return redirect(
            url_for("admin.list_users")
        )

    if user.is_active:
        message = (
            f"L'utilisateur {user.username} a été réactivé."
        )
    else:
        message = (
            f"L'utilisateur {user.username} a été désactivé."
        )

    flash(message, "success")

    return redirect(
        url_for("admin.list_users")
    )
