#!/usr/bin/env python3
"""Client asynchrone de l'API Produit externe."""

from typing import Any

import httpx

from clients.errors import (
    ExternalServiceResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    InvalidClientParameterError,
    ResourceNotFoundError,
)


class ProductAPIClient:
    """Consulte le catalogue de produits externe en lecture seule."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialise le client avec l'URL du service Produit."""

        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None

        self._client = http_client or httpx.AsyncClient(
            timeout=timeout,
        )

    async def list_products(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Retourne une page validée du catalogue Produit."""

        _validate_limit(limit)
        _validate_offset(offset)

        data = await self._get_json(
            "/api/v1/products",
            params={
                "limit": limit,
                "offset": offset,
            },
        )

        return _validate_product_page(data)

    async def get_product_details(
        self,
        product_id: int,
    ) -> dict[str, Any]:
        """Retourne les informations validées d'un produit."""

        _validate_positive_identifier(
            product_id,
            "product_id",
        )

        data = await self._get_json(
            f"/api/v1/products/{product_id}"
        )

        product = _validate_product(data)

        if product["id"] != product_id:
            raise ExternalServiceResponseError(
                "L'API Produit a retourné un identifiant différent "
                "de celui demandé."
            )

        return product

    async def _get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Exécute une requête GET et valide la racine JSON."""

        url = f"{self._base_url}{path}"

        try:
            response = await self._client.get(
                url,
                params=params,
            )

        except httpx.TimeoutException as error:
            raise ExternalServiceTimeoutError(
                "L'API Produit a dépassé le délai de réponse."
            ) from error

        except httpx.RequestError as error:
            raise ExternalServiceUnavailableError(
                "L'API Produit est injoignable."
            ) from error

        if response.status_code == 404:
            raise ResourceNotFoundError(
                "Le produit demandé n'existe pas."
            )

        if not 200 <= response.status_code < 300:
            raise ExternalServiceResponseError(
                "L'API Produit a répondu avec le code "
                f"{response.status_code}."
            )

        try:
            data = response.json()

        except ValueError as error:
            raise ExternalServiceResponseError(
                "L'API Produit a retourné un JSON invalide."
            ) from error

        if not isinstance(data, dict):
            raise ExternalServiceResponseError(
                "La réponse de l'API Produit doit être un objet JSON."
            )

        return data

    async def aclose(self) -> None:
        """Ferme le client HTTP créé par cette instance."""

        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self):
        """Retourne le client dans un contexte asynchrone."""

        return self

    async def __aexit__(
        self,
        _exception_type,
        _exception,
        _traceback,
    ) -> None:
        """Ferme proprement le client HTTP."""

        await self.aclose()


def _validate_product_page(
    data: dict[str, Any],
) -> dict[str, Any]:
    """Valide une réponse paginée de l'API Produit."""

    count = data.get("count")
    limit = data.get("limit")
    offset = data.get("offset")
    results = data.get("results")

    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
    ):
        raise ExternalServiceResponseError(
            "Le champ count de l'API Produit est invalide."
        )

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 100
    ):
        raise ExternalServiceResponseError(
            "Le champ limit de l'API Produit est invalide."
        )

    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
    ):
        raise ExternalServiceResponseError(
            "Le champ offset de l'API Produit est invalide."
        )

    if not isinstance(results, list):
        raise ExternalServiceResponseError(
            "Le champ results de l'API Produit doit être une liste."
        )

    validated_results = [
        _validate_product(product)
        for product in results
    ]

    return {
        "count": count,
        "limit": limit,
        "offset": offset,
        "results": validated_results,
    }


def _validate_product(
    product: Any,
) -> dict[str, Any]:
    """Valide les champs essentiels d'un produit."""

    if not isinstance(product, dict):
        raise ExternalServiceResponseError(
            "Un produit retourné par l'API est invalide."
        )

    product_id = product.get("id")
    sku = product.get("sku")
    name = product.get("name")
    description = product.get("description")
    category = product.get("category")
    unit_price = product.get("unit_price")

    _validate_response_identifier(product_id)

    for field_name, value in (
        ("sku", sku),
        ("name", name),
        ("category", category),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ExternalServiceResponseError(
                f"Le champ {field_name} du produit est invalide."
            )

    if not isinstance(description, str):
        raise ExternalServiceResponseError(
            "Le champ description du produit est invalide."
        )

    if (
        isinstance(unit_price, bool)
        or not isinstance(unit_price, (int, float))
        or unit_price < 0
    ):
        raise ExternalServiceResponseError(
            "Le champ unit_price du produit est invalide."
        )

    return product


def _validate_response_identifier(value: Any) -> int:
    """Valide un identifiant reçu depuis l'API Produit."""

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ExternalServiceResponseError(
            "L'identifiant retourné par l'API Produit est invalide."
        )

    return value


def _validate_positive_identifier(
    value: Any,
    field_name: str,
) -> int:
    """Valide un identifiant fourni au client."""

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise InvalidClientParameterError(
            f"{field_name} doit être un entier strictement positif."
        )

    return value


def _validate_limit(limit: Any) -> int:
    """Valide la taille demandée pour une page."""

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 100
    ):
        raise InvalidClientParameterError(
            "limit doit être un entier compris entre 1 et 100."
        )

    return limit


def _validate_offset(offset: Any) -> int:
    """Valide le décalage demandé pour une page."""

    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
    ):
        raise InvalidClientParameterError(
            "offset doit être un entier positif ou nul."
        )

    return offset
