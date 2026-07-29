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

    if not base_url:
        raise ProductApiError(
            "La variable PRODUCT_API_BASE_URL est manquante."
        )

    return base_url.rstrip("/")


def _get(path: str, params: dict | None = None) -> dict:
    """Appelle l'API Produit en GET et retourne une réponse JSON valide."""

    url = f"{_base_url()}/api/v1{path}"

    try:
        response = requests.get(
            url,
            params=params,
            timeout=_TIMEOUT,
        )

    except requests.RequestException as error:
        raise ProductApiError(
            "L'API Produit est injoignable."
        ) from error

    if response.status_code == 404:
        raise ProductNotFoundError("Produit introuvable.")

    if not response.ok:
        raise ProductApiError(
            "L'API Produit a répondu avec le code "
            f"{response.status_code}."
        )

    try:
        data = response.json()

    except (ValueError, requests.exceptions.JSONDecodeError) as error:
        raise ProductApiError(
            "L'API Produit a retourné un JSON invalide."
        ) from error

    if not isinstance(data, dict):
        raise ProductApiError(
            "La structure retournée par l'API Produit est invalide."
        )

    return data


def get_product(product_id: int) -> dict:
    """Retourne les détails d'un produit à partir de son identifiant."""

    product = _get(f"/products/{product_id}")

    if "id" not in product:
        raise ProductApiError(
            "La réponse de l'API Produit ne contient aucun identifiant."
        )

    return product


def search_products(query: str) -> list[dict]:
    """Retourne les produits correspondant à un mot-clé de recherche."""

    data = _get(
        "/products/search",
        params={"q": query},
    )

    results = data.get("results")

    if not isinstance(results, list):
        raise ProductApiError(
            "La liste de résultats de l'API Produit est invalide."
        )

    if not all(isinstance(product, dict) for product in results):
        raise ProductApiError(
            "Un résultat retourné par l'API Produit est invalide."
        )

    return results


def list_products(limit: int = 20, offset: int = 0) -> dict:
    """Retourne une page de produits avec ses informations de pagination."""

    return _get(
        "/products",
        params={
            "limit": limit,
            "offset": offset,
        },
    )
