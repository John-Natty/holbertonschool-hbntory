#!/usr/bin/env python3
"""Client asynchrone de l'API interne du Backoffice."""

from typing import Any

import httpx

from clients.errors import (
    ExternalServiceResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    InvalidClientParameterError,
    ResourceNotFoundError,
)


class BackofficeAPIClient:
    """Consulte les stocks du Backoffice en lecture seule."""

    def __init__(
        self,
        base_url: str,
        internal_api_key: str,
        *,
        timeout: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialise le client de l'API interne."""

        self._base_url = base_url.rstrip("/")
        self._internal_api_key = internal_api_key
        self._owns_client = http_client is None

        self._client = http_client or httpx.AsyncClient(
            timeout=timeout,
        )

    async def get_stock_by_product(
        self,
        product_id: int,
    ) -> dict[str, Any]:
        """Retourne les branches possédant un produit."""

        _validate_positive_identifier(
            product_id,
            "product_id",
        )

        data = await self._request_json(
            "GET",
            f"/internal/stocks/products/{product_id}",
        )

        returned_product_id = data.get("product_id")
        branches = data.get("branches")

        if returned_product_id != product_id:
            raise ExternalServiceResponseError(
                "Le Backoffice a retourné un identifiant produit "
                "différent de celui demandé."
            )

        if not isinstance(branches, list):
            raise ExternalServiceResponseError(
                "Le champ branches du Backoffice doit être une liste."
            )

        return {
            "product_id": returned_product_id,
            "branches": [
                _validate_product_branch(branch)
                for branch in branches
            ],
        }

    async def get_stock_by_branch(
        self,
        branch_id: int,
    ) -> dict[str, Any]:
        """Retourne les produits disponibles dans une branche."""

        _validate_positive_identifier(
            branch_id,
            "branch_id",
        )

        data = await self._request_json(
            "GET",
            f"/internal/stocks/branches/{branch_id}",
        )

        branch = _validate_branch(data.get("branch"))
        stocks = data.get("stocks")

        if branch["id"] != branch_id:
            raise ExternalServiceResponseError(
                "Le Backoffice a retourné une branche différente "
                "de celle demandée."
            )

        if not isinstance(stocks, list):
            raise ExternalServiceResponseError(
                "Le champ stocks du Backoffice doit être une liste."
            )

        return {
            "branch": branch,
            "stocks": [
                _validate_stock(stock)
                for stock in stocks
            ],
        }

    async def check_shopping_list(
        self,
        items: list[dict[str, int]],
    ) -> dict[str, Any]:
        """Retourne les branches pouvant satisfaire une liste d'achats."""

        validated_items = _validate_requested_items(items)
        expected_quantities = {
            item["product_id"]: item["quantity"]
            for item in validated_items
        }

        data = await self._request_json(
            "POST",
            "/internal/stocks/check-shopping-list",
            json={
                "items": validated_items,
            },
        )

        matching_branches = data.get("matching_branches")

        if not isinstance(matching_branches, list):
            raise ExternalServiceResponseError(
                "Le champ matching_branches doit être une liste."
            )

        return {
            "matching_branches": [
                _validate_matching_branch(
                    branch,
                    expected_quantities,
                )
                for branch in matching_branches
            ],
        }

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Appelle le Backoffice et valide sa réponse JSON."""

        url = f"{self._base_url}{path}"

        try:
            response = await self._client.request(
                method,
                url,
                headers={
                    "X-Internal-API-Key": self._internal_api_key,
                },
                json=json,
            )

        except httpx.TimeoutException as error:
            raise ExternalServiceTimeoutError(
                "Le Backoffice a dépassé le délai de réponse."
            ) from error

        except httpx.RequestError as error:
            raise ExternalServiceUnavailableError(
                "Le Backoffice est injoignable."
            ) from error

        try:
            data = response.json()

        except ValueError as error:
            raise ExternalServiceResponseError(
                "Le Backoffice a retourné un JSON invalide."
            ) from error

        if not isinstance(data, dict):
            raise ExternalServiceResponseError(
                "La réponse du Backoffice doit être un objet JSON."
            )

        if response.status_code == 404:
            raise ResourceNotFoundError(
                _extract_error_message(
                    data,
                    "La ressource demandée n'existe pas.",
                )
            )

        if not 200 <= response.status_code < 300:
            raise ExternalServiceResponseError(
                _extract_error_message(
                    data,
                    "Le Backoffice a retourné une erreur HTTP "
                    f"{response.status_code}.",
                )
            )

        if data.get("success") is not True:
            raise ExternalServiceResponseError(
                _extract_error_message(
                    data,
                    "La réponse du Backoffice indique un échec.",
                )
            )

        if data.get("error") is not None:
            raise ExternalServiceResponseError(
                "La réponse réussie du Backoffice contient une erreur."
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


def _validate_product_branch(
    branch: Any,
) -> dict[str, Any]:
    """Valide une branche associée à un produit."""

    if not isinstance(branch, dict):
        raise ExternalServiceResponseError(
            "Une branche retournée par le Backoffice est invalide."
        )

    branch_id = branch.get("branch_id")
    branch_name = branch.get("branch_name")
    quantity = branch.get("quantity")

    _validate_response_identifier(branch_id, "branch_id")
    _validate_non_negative_quantity(quantity, "quantity")

    if not isinstance(branch_name, str) or not branch_name.strip():
        raise ExternalServiceResponseError(
            "Le nom d'une branche retournée est invalide."
        )

    return {
        "branch_id": branch_id,
        "branch_name": branch_name,
        "quantity": quantity,
    }


def _validate_branch(branch: Any) -> dict[str, Any]:
    """Valide les informations d'une branche."""

    if not isinstance(branch, dict):
        raise ExternalServiceResponseError(
            "Le champ branch du Backoffice est invalide."
        )

    branch_id = branch.get("id")
    branch_name = branch.get("name")

    _validate_response_identifier(branch_id, "branch_id")

    if not isinstance(branch_name, str) or not branch_name.strip():
        raise ExternalServiceResponseError(
            "Le nom de la branche est invalide."
        )

    return {
        "id": branch_id,
        "name": branch_name,
    }


def _validate_stock(stock: Any) -> dict[str, int]:
    """Valide une ligne de stock."""

    if not isinstance(stock, dict):
        raise ExternalServiceResponseError(
            "Une ligne de stock retournée est invalide."
        )

    product_id = stock.get("product_id")
    quantity = stock.get("quantity")

    _validate_response_identifier(product_id, "product_id")
    _validate_non_negative_quantity(quantity, "quantity")

    return {
        "product_id": product_id,
        "quantity": quantity,
    }


def _validate_matching_branch(
    branch: Any,
    expected_quantities: dict[int, int],
) -> dict[str, Any]:
    """Valide une branche satisfaisant une liste d'achats."""

    if not isinstance(branch, dict):
        raise ExternalServiceResponseError(
            "Une branche correspondante est invalide."
        )

    branch_id = branch.get("branch_id")
    branch_name = branch.get("branch_name")
    items = branch.get("items")

    _validate_response_identifier(branch_id, "branch_id")

    if not isinstance(branch_name, str) or not branch_name.strip():
        raise ExternalServiceResponseError(
            "Le nom d'une branche correspondante est invalide."
        )

    if not isinstance(items, list):
        raise ExternalServiceResponseError(
            "Le champ items d'une branche doit être une liste."
        )

    validated_items = []
    returned_product_ids = set()

    for item in items:
        validated_item = _validate_matching_item(item)
        product_id = validated_item["product_id"]

        if product_id in returned_product_ids:
            raise ExternalServiceResponseError(
                "Une branche correspondante contient "
                "un produit dupliqué."
            )

        if product_id not in expected_quantities:
            raise ExternalServiceResponseError(
                "Une branche correspondante contient "
                "un produit qui n'a pas été demandé."
            )

        expected_quantity = expected_quantities[product_id]

        if (
            validated_item["requested_quantity"]
            != expected_quantity
        ):
            raise ExternalServiceResponseError(
                "La quantité demandée retournée par le Backoffice "
                "ne correspond pas à la liste envoyée."
            )

        returned_product_ids.add(product_id)
        validated_items.append(validated_item)

    missing_product_ids = (
        set(expected_quantities)
        - returned_product_ids
    )

    if missing_product_ids:
        raise ExternalServiceResponseError(
            "Une branche correspondante ne contient pas "
            "tous les produits demandés."
        )

    return {
        "branch_id": branch_id,
        "branch_name": branch_name,
        "items": validated_items,
    }


def _validate_matching_item(item: Any) -> dict[str, int]:
    """Valide un produit d'une liste satisfaite."""

    if not isinstance(item, dict):
        raise ExternalServiceResponseError(
            "Un élément de liste retourné est invalide."
        )

    product_id = item.get("product_id")
    requested_quantity = item.get("requested_quantity")
    available_quantity = item.get("available_quantity")

    _validate_response_identifier(product_id, "product_id")
    _validate_positive_quantity(
        requested_quantity,
        "requested_quantity",
    )
    _validate_non_negative_quantity(
        available_quantity,
        "available_quantity",
    )

    if available_quantity < requested_quantity:
        raise ExternalServiceResponseError(
            "Une branche annoncée comme correspondante "
            "ne possède pas la quantité demandée."
        )

    return {
        "product_id": product_id,
        "requested_quantity": requested_quantity,
        "available_quantity": available_quantity,
    }


def _validate_requested_items(
    items: Any,
) -> list[dict[str, int]]:
    """Valide et normalise une liste d'achats avant son envoi."""

    if not isinstance(items, list) or not items:
        raise InvalidClientParameterError(
            "items doit être une liste non vide."
        )

    quantities_by_product = {}
    product_order = []

    for item in items:
        if not isinstance(item, dict):
            raise InvalidClientParameterError(
                "Chaque élément de items doit être un objet."
            )

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        _validate_positive_identifier(
            product_id,
            "product_id",
        )
        _validate_positive_client_quantity(
            quantity,
            "quantity",
        )

        if product_id not in quantities_by_product:
            product_order.append(product_id)
            quantities_by_product[product_id] = 0

        quantities_by_product[product_id] += quantity

    return [
        {
            "product_id": product_id,
            "quantity": quantities_by_product[product_id],
        }
        for product_id in product_order
    ]


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


def _validate_positive_client_quantity(
    value: Any,
    field_name: str,
) -> int:
    """Valide une quantité fournie au client."""

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise InvalidClientParameterError(
            f"{field_name} doit être un entier strictement positif."
        )

    return value


def _validate_response_identifier(
    value: Any,
    field_name: str,
) -> int:
    """Valide un identifiant reçu depuis le Backoffice."""

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ExternalServiceResponseError(
            f"Le champ {field_name} retourné est invalide."
        )

    return value


def _validate_positive_quantity(
    value: Any,
    field_name: str,
) -> int:
    """Valide une quantité strictement positive reçue."""

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ExternalServiceResponseError(
            f"Le champ {field_name} retourné est invalide."
        )

    return value


def _validate_non_negative_quantity(
    value: Any,
    field_name: str,
) -> int:
    """Valide une quantité positive ou nulle reçue."""

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ExternalServiceResponseError(
            f"Le champ {field_name} retourné est invalide."
        )

    return value


def _extract_error_message(
    data: dict[str, Any],
    default_message: str,
) -> str:
    """Extrait un message d'erreur structuré du Backoffice."""

    error = data.get("error")

    if not isinstance(error, dict):
        return default_message

    message = error.get("message")

    if not isinstance(message, str) or not message.strip():
        return default_message

    return message
