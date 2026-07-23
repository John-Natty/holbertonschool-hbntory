"""Formulaires utilisés pour administrer les utilisateurs."""

from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    EqualTo,
    Length,
    Optional,
)


class CreateUserForm(FlaskForm):
    """Formulaire permettant de créer un utilisateur common."""

    username = StringField(
        "Nom d'utilisateur",
        validators=[
            DataRequired(
                message="Le nom d'utilisateur est obligatoire."
            ),
            Length(
                min=3,
                max=80,
                message=(
                    "Le nom d'utilisateur doit contenir "
                    "entre 3 et 80 caractères."
                ),
            ),
        ],
    )

    password = PasswordField(
        "Mot de passe",
        validators=[
            DataRequired(
                message="Le mot de passe est obligatoire."
            ),
            Length(
                min=12,
                max=128,
                message=(
                    "Le mot de passe doit contenir "
                    "entre 12 et 128 caractères."
                ),
            ),
            EqualTo(
                "confirm_password",
                message=(
                    "Les deux mots de passe doivent être identiques."
                ),
            ),
        ],
    )

    confirm_password = PasswordField(
        "Confirmation du mot de passe",
        validators=[
            DataRequired(
                message="La confirmation est obligatoire."
            ),
        ],
    )

    branch_id = SelectField(
        "Branche",
        coerce=int,
        validators=[
            DataRequired(
                message="La branche est obligatoire."
            ),
        ],
    )

    submit = SubmitField("Créer l'utilisateur")


class EditUserForm(FlaskForm):
    """Formulaire permettant de modifier un utilisateur common."""

    username = StringField(
        "Nom d'utilisateur",
        validators=[
            DataRequired(
                message="Le nom d'utilisateur est obligatoire."
            ),
            Length(
                min=3,
                max=80,
                message=(
                    "Le nom d'utilisateur doit contenir "
                    "entre 3 et 80 caractères."
                ),
            ),
        ],
    )

    password = PasswordField(
        "Nouveau mot de passe",
        validators=[
            # Le champ peut rester vide pour conserver
            # le mot de passe actuel.
            Optional(),
            Length(
                min=12,
                max=128,
                message=(
                    "Le nouveau mot de passe doit contenir "
                    "entre 12 et 128 caractères."
                ),
            ),
            EqualTo(
                "confirm_password",
                message=(
                    "Les deux mots de passe doivent être identiques."
                ),
            ),
        ],
    )

    confirm_password = PasswordField(
        "Confirmation du nouveau mot de passe",
        validators=[
            # La confirmation reste facultative lorsque
            # le mot de passe n'est pas modifié.
            Optional(),
        ],
    )

    branch_id = SelectField(
        "Branche",
        coerce=int,
        validators=[
            DataRequired(
                message="La branche est obligatoire."
            ),
        ],
    )

    submit = SubmitField("Enregistrer les modifications")
