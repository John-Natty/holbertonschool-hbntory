#!/usr/bin/env python3
"""Outils MCP permettant de consulter les stocks du Backoffice."""

from typing import Any

from clients.backoffice_api import BackofficeAPIClient
from clients.errors import MCPClientError
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
    client: BackofficeAPIClient,
    branch_id: int,
) -> dict[str, Any]:
    """Retourne les produits disponibles dans une branche."""

    try:
        result = await client.get_stock_by_branch(branch_id)

    except MCPClientError as error:
        # Empêche l'exposition d'une traceback technique à l'agent.
        return error_response(error)

    return success_response(
        branch=result["branch"],
        stocks=result["stocks"],
    )


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
