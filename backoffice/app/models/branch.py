"""Modèle représentant une branche."""

from sqlalchemy import Index, func

from app.extensions import db


class Branch(db.Model):
    """Représente une branche de HBntory."""

    __tablename__ = "branches"

    # Identifiant unique de la branche.
    id = db.Column(db.Integer, primary_key=True)

    # Nom affiché de la branche.
    name = db.Column(db.String(100), nullable=False)

    # Empêche la création de deux branches ayant le même nom,
    # sans tenir compte des majuscules et des minuscules.
    __table_args__ = (
        Index(
            "uq_branches_name_lower",
            func.lower(name),
            unique=True,
        ),
    )

    # Liste des utilisateurs rattachés à cette branche.
    users = db.relationship(
        "User",
        back_populates="branch",
    )

    # Liste des stocks appartenant à cette branche.
    stocks = db.relationship(
        "Stock",
        back_populates="branch",
    )

    def __repr__(self):
        """Retourne une représentation lisible de la branche."""
        return f"<Branch id={self.id} name={self.name!r}>"
