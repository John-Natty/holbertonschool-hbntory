#!/usr/bin/env python3
"""Client asynchrone de l'API Produit externe."""

from typing import Any

import httpx
from pydantic import ValidationError

from clients.errors import (
    ExternalServiceResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    InvalidClientParameterError,
    ResourceNotFoundError,
)
from schemas import ProductSchema


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

        return _validate_product_page(
            data,
            expected_limit=limit,
            expected_offset=offset,
        )

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
    *,
    expected_limit: int,
    expected_offset: int,
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

    if limit != expected_limit:
        raise ExternalServiceResponseError(
            "Le champ limit de l'API Produit ne correspond pas "
            "à la pagination demandée."
        )

    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
    ):
        raise ExternalServiceResponseError(
            "Le champ offset de l'API Produit est invalide."
        )

    if offset != expected_offset:
        raise ExternalServiceResponseError(
            "Le champ offset de l'API Produit ne correspond pas "
            "à la pagination demandée."
        )

    if not isinstance(results, list):
        raise ExternalServiceResponseError(
            "Le champ results de l'API Produit doit être une liste."
        )

    if len(results) > limit:
        raise ExternalServiceResponseError(
            "L'API Produit a retourné plus de résultats que "
            "la limite demandée."
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
    """Valide un produit avec le contrat Pydantic complet."""

    if not isinstance(product, dict):
        raise ExternalServiceResponseError(
            "Un produit retourné par l'API est invalide."
        )

    try:
        validated_product = ProductSchema.model_validate(
            product
        )

    except ValidationError as error:
        raise ExternalServiceResponseError(
            "Un produit retourné par l'API Produit "
            "ne respecte pas le contrat attendu."
        ) from error

    return validated_product.model_dump(
        mode="json",
    )


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
