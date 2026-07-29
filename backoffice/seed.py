#!/usr/bin/env python3
"""Initialise les données de base du Backoffice HBntory."""

import os
import sys

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import Branch, User


def get_or_create_branch(name):
    """Récupère une branche existante ou crée une nouvelle branche."""
    # Vérifie que le nom reçu est bien une chaîne de caractères.
    if not isinstance(name, str):
        raise ValueError(
            "Le nom de la branche doit être une chaîne de caractères."
        )

    # Supprime les espaces inutiles autour du nom.
    normalized_name = name.strip()

    # Refuse un nom vide ou composé uniquement d'espaces.
    if not normalized_name:
        raise ValueError(
            "Le nom de la branche ne peut pas être vide."
        )

    # Recherche une branche existante sans tenir compte de la casse.
    branch = db.session.scalar(
        select(Branch).where(
            func.lower(Branch.name) == normalized_name.lower()
        )
    )

    # Retourne la branche si elle existe déjà.
    if branch is not None:
        print(f"Branche déjà présente : {branch.name}")
        return branch

    # Crée une nouvelle branche.
    branch = Branch(name=normalized_name)

    # Ajoute la branche à la session SQLAlchemy.
    db.session.add(branch)

    print(f"Branche créée : {branch.name}")
    return branch


def get_or_create_admin(username, password):
    """Récupère l'administrateur existant ou crée le compte initial."""
    # Recherche d'abord un administrateur existant.
    existing_admin = db.session.scalar(
        select(User).where(User.role == "admin")
    )

    # Ne crée pas de deuxième administrateur.
    if existing_admin is not None:
        print(
            "Administrateur déjà présent : "
            f"{existing_admin.username}"
        )
        return existing_admin

    # Vérifie que le username est une chaîne de caractères.
    if not isinstance(username, str):
        raise ValueError(
            "Le username administrateur doit être une chaîne."
        )

    # Nettoie et normalise le username.
    normalized_username = username.strip().lower()

    # Refuse un username vide.
    if not normalized_username:
        raise ValueError(
            "Le username administrateur ne peut pas être vide."
        )

    # Vérifie que le username n'est pas déjà utilisé.
    existing_user = db.session.scalar(
        select(User).where(
            func.lower(User.username) == normalized_username
        )
    )

    if existing_user is not None:
        raise ValueError(
            "Le username choisi est déjà utilisé par un autre compte."
        )

    # Crée l'administrateur sans branche.
    admin = User(
        username=normalized_username,
        role="admin",
        is_active=True,
        branch_id=None,
    )

    # Hache le mot de passe avec bcrypt.
    # Le mot de passe en clair n'est jamais enregistré.
    admin.set_password(password)

    # Ajoute l'administrateur à la session SQLAlchemy.
    db.session.add(admin)

    print(f"Administrateur créé : {admin.username}")
    return admin


def seed_database():
    """Crée les données initiales de manière réexécutable."""
    # Récupère le username administrateur depuis l'environnement.
    admin_username = os.getenv(
        "SEED_ADMIN_USERNAME",
        "admin",
    )

    # Le mot de passe n'a volontairement aucune valeur par défaut.
    admin_password = os.getenv("SEED_ADMIN_PASSWORD")

    # Récupère les noms des deux branches initiales.
    branch_one_name = os.getenv(
        "SEED_BRANCH_1_NAME",
        "Toulouse",
    )
    branch_two_name = os.getenv(
        "SEED_BRANCH_2_NAME",
        "Carcassonne",
    )

    # Refuse de continuer sans mot de passe administrateur.
    if not admin_password:
        raise RuntimeError(
            "La variable SEED_ADMIN_PASSWORD est manquante."
        )

    # Empêche la création de deux branches portant le même nom.
    if branch_one_name.strip().lower() == branch_two_name.strip().lower():
        raise ValueError(
            "Les deux branches initiales doivent avoir "
            "des noms différents."
        )

    # Crée l'application Flask.
    app = create_app()

    # Active le contexte nécessaire pour utiliser SQLAlchemy.
    with app.app_context():
        try:
            # Crée les deux branches si elles n'existent pas.
            get_or_create_branch(branch_one_name)
            get_or_create_branch(branch_two_name)

            # Crée l'administrateur initial s'il n'existe pas.
            get_or_create_admin(
                admin_username,
                admin_password,
            )

            # Enregistre toutes les modifications dans PostgreSQL.
            db.session.commit()

            print(
                "Initialisation de la base terminée avec succès."
            )

        except (ValueError, RuntimeError, SQLAlchemyError):
            # Annule toutes les modifications en cas d'erreur.
            db.session.rollback()
            raise


def main():
    """Exécute le script et retourne un code de sortie."""
    try:
        seed_database()

    except (ValueError, RuntimeError, SQLAlchemyError) as error:
        # Affiche une erreur lisible et retourne un code d'échec.
        print(f"Erreur pendant l'initialisation : {error}")
        return 1

    # Retourne zéro lorsque l'initialisation réussit.
    return 0


if __name__ == "__main__":
    sys.exit(main())
