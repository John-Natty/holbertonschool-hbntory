"""Formulaires liés à l'authentification."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import InputRequired, Length


class LoginForm(FlaskForm):
    """Formulaire permettant à un utilisateur de se connecter."""

    username = StringField(
        "Nom d'utilisateur",
        validators=[
            InputRequired(
                message="Le nom d'utilisateur est obligatoire."
            ),
            Length(
                max=80,
                message=(
                    "Le nom d'utilisateur ne peut pas dépasser "
                    "80 caractères."
                ),
            ),
        ],
    )

    password = PasswordField(
        "Mot de passe",
        validators=[
            InputRequired(
                message="Le mot de passe est obligatoire."
            ),
        ],
    )

    remember = BooleanField("Rester connecté")

    submit = SubmitField("Se connecter")
