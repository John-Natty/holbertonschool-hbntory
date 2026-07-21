#!/usr/bin/env python3
"""Branch model"""

from ..extensions import db


class Branch(db.Model):
    """A store branch that owns users and stock entries"""

    __tablename__ = "branches"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    users = db.relationship("User", back_populates="branch")
    stocks = db.relationship("Stock", back_populates="branch")
