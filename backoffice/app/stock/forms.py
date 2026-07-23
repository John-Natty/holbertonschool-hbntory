"""Formulaires utilisés pour gérer le stock d'une branche."""

from flask_wtf import FlaskForm
from wtforms import IntegerField
from wtforms.validators import InputRequired, NumberRange


class StockMovementForm(FlaskForm):
    """Formulaire d'ajout ou de retrait d'une quantité de produit."""

    product_id = IntegerField(
        "Identifiant du produit",
        validators=[
            InputRequired(
                message="L'identifiant du produit est obligatoire."
            ),
            NumberRange(
                min=1,
                message=(
                    "L'identifiant du produit doit être "
                    "un entier positif."
                ),
            ),
        ],
    )

    amount = IntegerField(
        "Quantité",
        validators=[
            InputRequired(
                message="La quantité est obligatoire."
            ),
            NumberRange(
                min=1,
                message=(
                    "La quantité doit être strictement positive."
                ),
            ),
        ],
    )
