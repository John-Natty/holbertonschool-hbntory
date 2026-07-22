"""Modèle représentant une ligne de stock."""

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text

from app.extensions import db


class Stock(db.Model):
    """Représente la quantité d'un produit dans une branche."""

    __tablename__ = "stocks"

    __table_args__ = (
        # Empêche une quantité de stock négative.
        CheckConstraint(
            "quantity >= 0",
            name="ck_stocks_quantity_non_negative",
        ),

        # Empêche deux lignes pour le même produit dans une branche.
        UniqueConstraint(
            "branch_id",
            "product_id",
            name="uq_stocks_branch_product",
        ),

        # Accélère la recherche des stocks à partir d'un produit.
        Index(
            "ix_stocks_product_id",
            "product_id",
        ),
    )

    # Identifiant unique de la ligne de stock.
    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # Branche propriétaire de la ligne de stock.
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "branches.id",
            name="fk_stocks_branch",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # Identifiant numérique provenant de l'API Produit externe.
    # Il ne correspond à aucune clé étrangère locale.
    product_id = db.Column(
        db.Integer,
        nullable=False,
    )

    # Quantité disponible dans la branche.
    quantity = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    # Relation vers la branche propriétaire du stock.
    branch = db.relationship(
        "Branch",
        back_populates="stocks",
    )

    def __repr__(self):
        """Retourne une représentation lisible du stock."""
        return (
            f"<Stock id={self.id} "
            f"branch_id={self.branch_id} "
            f"product_id={self.product_id} "
            f"quantity={self.quantity}>"
        )
