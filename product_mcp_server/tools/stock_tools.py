#!/usr/bin/env python3
"""Outils MCP permettant de consulter les stocks du Backoffice."""

import asyncio
from typing import Any

from pydantic import ValidationError

from clients.backoffice_api import BackofficeAPIClient
from clients.errors import (
    InvalidClientParameterError,
    MCPClientError,
)
from clients.product_api import ProductAPIClient
from schemas import BranchReferenceInput
from tools.responses import error_response, success_response


async def get_stock_by_product_tool(
    client: BackofficeAPIClient,
    product_id: int,
) -> dict[str, Any]:
    """Retourne les branches possédant un produit en stock."""

    try:
        result = await client.get_stock_by_product(product_id)

    except MCPClientError as error:
        # Transforme une erreur connue en réponse compréhensible par l'IA.
        return error_response(error)

    return success_response(
        product_id=result["product_id"],
        branches=result["branches"],
    )


async def get_stock_by_branch_tool(
    backoffice_client: BackofficeAPIClient,
    product_client: ProductAPIClient,
    branch_id: int | None = None,
    branch_name: str | None = None,
) -> dict[str, Any]:
    """Retourne le stock enrichi avec les noms officiels Produit."""

    try:
        try:
            reference = BranchReferenceInput(
                branch_id=branch_id,
                branch_name=branch_name,
            )
        except ValidationError as error:
            raise InvalidClientParameterError(
                "Fournissez soit branch_id, soit branch_name."
            ) from error

        if (
            reference.branch_id is not None
            and reference.branch_name is not None
        ):
            result = await backoffice_client.get_stock_by_branch(
                branch_id=reference.branch_id,
                branch_name=reference.branch_name,
            )
        elif reference.branch_name is None:
            result = await backoffice_client.get_stock_by_branch(
                reference.branch_id
            )
        else:
            result = await backoffice_client.get_stock_by_branch(
                branch_name=reference.branch_name
            )

        enriched_stocks = await _enrich_stocks_with_product_details(
            product_client,
            result["stocks"],
        )

    except MCPClientError as error:
        # Empêche l'exposition d'une traceback technique à l'agent.
        return error_response(error)

    return success_response(
        branch=result["branch"],
        stocks=enriched_stocks,
    )


async def _enrich_stocks_with_product_details(
    product_client: ProductAPIClient,
    stocks: list[dict[str, int]],
) -> list[dict[str, Any]]:
    """Associe chaque quantité au nom et au prix officiels du produit."""

    products = await asyncio.gather(
        *(
            product_client.get_product_details(
                stock["product_id"]
            )
            for stock in stocks
        )
    )

    return [
        {
            "product_id": stock["product_id"],
            "product_name": product["name"],
            "unit_price": product["unit_price"],
            "currency": product["currency"],
            "quantity": stock["quantity"],
        }
        for stock, product in zip(
            stocks,
            products,
            strict=True,
        )
    ]


async def check_shopping_list_tool(
    client: BackofficeAPIClient,
    items: list[dict[str, int]],
) -> dict[str, Any]:
    """Retourne les branches pouvant satisfaire toute une liste d'achats."""

    try:
        result = await client.check_shopping_list(items)

    except MCPClientError as error:
        # Retourne une erreur structurée en cas de requête invalide
        # ou d'indisponibilité du Backoffice.
        return error_response(error)

    return success_response(
        matching_branches=result["matching_branches"],
    )
