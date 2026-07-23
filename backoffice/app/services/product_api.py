#!/usr/bin/env python3
"""Client de l'API Produit externe pour le Backoffice."""

import os

import requests


class ProductApiError(Exception):
    """Erreur levée quand l'API Produit est indisponible ou répond mal."""


class ProductNotFoundError(ProductApiError):
    """Erreur levée quand un produit demandé n'existe pas."""


# Délai maximum d'attente d'une réponse de l'API, en secondes.
_TIMEOUT = 5


def _base_url() -> str:
    """Retourne l'URL de base de l'API Produit depuis l'environnement."""

    base_url = os.getenv("PRODUCT_API_BASE_URL")

    # L'URL est obligatoire pour joindre l'API.
    if not base_url:
        raise ProductApiError(
            "La variable PRODUCT_API_BASE_URL est manquante."
        )

    return base_url.rstrip("/")


def _get(path: str, params: dict | None = None) -> dict:
    """Appelle l'API Produit en GET et retourne la réponse JSON."""

    url = f"{_base_url()}/api/v1{path}"

    # Contacte l'API en gérant les pannes réseau et les délais.
    try:
        response = requests.get(url, params=params, timeout=_TIMEOUT)
    except requests.RequestException as error:
        raise ProductApiError("L'API Produit est injoignable.") from error

    # Un code 404 correspond à une ressource inexistante.
    if response.status_code == 404:
        raise ProductNotFoundError("Produit introuvable.")

    # Toute autre erreur HTTP est signalée clairement.
    if not response.ok:
        raise ProductApiError(
            f"L'API Produit a répondu avec le code {response.status_code}."
        )

    return response.json()


def get_product(product_id: int) -> dict:
    """Retourne les détails d'un produit à partir de son identifiant."""

    return _get(f"/products/{product_id}")


def search_products(query: str) -> list[dict]:
    """Retourne les produits correspondant à un mot-clé de recherche."""

    data = _get("/products/search", params={"q": query})

    # Les résultats sont rangés sous la clé "results".
    return data.get("results", [])


def list_products(limit: int = 20, offset: int = 0) -> dict:
    """Retourne une page de produits avec ses infos de pagination."""

    return _get("/products", params={"limit": limit, "offset": offset})
