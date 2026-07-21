#!/usr/bin/env python3
"""Stock model"""

from ..extensions import db


class Stock(db.Model):
    """A quantity of a given product held in a given branch"""

    __tablename__ = "stocks"
    __table_args__ = (
        db.UniqueConstraint(
            "branch_id",
            "product_id",
            name="uq_stocks_branch_product",
        ),
        db.CheckConstraint(
            "quantity >= 0",
            name="ck_stocks_quantity_non_negative",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(
        db.Integer, db.ForeignKey("branches.id"), nullable=False
    )
    product_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)

    branch = db.relationship("Branch", back_populates="stocks")
