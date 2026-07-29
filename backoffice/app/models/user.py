"""Modèle représentant un utilisateur."""

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, func
from sqlalchemy.orm import validates

from app.extensions import bcrypt, db


class User(UserMixin, db.Model):
    """Représente un utilisateur du Backoffice."""

    __tablename__ = "users"

    # Identifiant unique de l'utilisateur.
    id = db.Column(db.Integer, primary_key=True)

    # Identifiant utilisé pour la connexion.
    username = db.Column(db.String(80), nullable=False)

    # Contient uniquement le hash bcrypt du mot de passe.
    password_hash = db.Column(db.String(255), nullable=False)

    # Rôle de l'utilisateur : admin ou common.
    role = db.Column(db.String(20), nullable=False)

    # Permet de désactiver un compte sans le supprimer.
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )

    # Branche du common user.
    # Cette valeur reste vide pour l'administrateur.
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "branches.id",
            name="fk_users_branch",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    # Relation vers la branche de l'utilisateur.
    branch = db.relationship(
        "Branch",
        back_populates="users",
    )

    __table_args__ = (
        # Autorise uniquement les deux rôles prévus.
        CheckConstraint(
            "role IN ('admin', 'common')",
            name="ck_users_role_valid",
        ),

        # Un administrateur ne doit appartenir à aucune branche.
        CheckConstraint(
            "role != 'admin' OR branch_id IS NULL",
            name="ck_users_admin_without_branch",
        ),

        # Un common user doit obligatoirement avoir une branche.
        CheckConstraint(
            "role != 'common' OR branch_id IS NOT NULL",
            name="ck_users_common_with_branch",
        ),

        # Empêche les doublons comme jo, Jo et JO.
        Index(
            "uq_users_username_lower",
            func.lower(username),
            unique=True,
        ),
    )

    @validates("username")
    def normalize_username(self, _key, username):
        """Nettoie et normalise le username avant son enregistrement."""
        if not isinstance(username, str):
            raise ValueError(
                "Le username doit être une chaîne de caractères."
            )

        normalized_username = username.strip().lower()

        if not normalized_username:
            raise ValueError("Le username ne peut pas être vide.")

        return normalized_username

    def set_password(self, password):
        """Enregistre le mot de passe sous forme de hash bcrypt."""
        if not isinstance(password, str) or not password.strip():
            raise ValueError("Le mot de passe ne peut pas être vide.")

        self.password_hash = bcrypt.generate_password_hash(
            password
        ).decode("utf-8")

    def check_password(self, password):
        """Vérifie un mot de passe par rapport au hash enregistré."""
        return bcrypt.check_password_hash(
            self.password_hash,
            password,
        )

    def __repr__(self):
        """Retourne une représentation lisible de l'utilisateur."""
        return (
            f"<User id={self.id} "
            f"username={self.username!r} "
            f"role={self.role!r}>"
        )
