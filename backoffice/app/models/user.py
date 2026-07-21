#!/usr/bin/env python3
"""User model"""

from ..extensions import db


class User(db.Model):
    """An authenticated backoffice user, either admin or common"""

    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('admin', 'common')",
            name="ck_users_role",
        ),
        db.CheckConstraint(
            "(role = 'admin' AND branch_id IS NULL)"
            " OR (role = 'common' AND branch_id IS NOT NULL)",
            name="ck_users_branch_by_role",
        ),
        db.Index(
            "uq_users_single_admin",
            "role",
            unique=True,
            postgresql_where=db.text("role = 'admin'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"))

    branch = db.relationship("Branch", back_populates="users")
