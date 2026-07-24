#!/usr/bin/env python3
"""Outils MCP permettant de consulter le catalogue Produit."""

from typing import Any

from clients.errors import MCPClientError
from clients.product_api import ProductAPIClient
from tools.responses import error_response, success_response


async def list_products_tool(
    client: ProductAPIClient,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Retourne une page de produits depuis l'API Produit externe."""

    try:
        page = await client.list_products(
            limit=limit,
            offset=offset,
        )

    except MCPClientError as error:
        # Transforme uniquement les erreurs prévues du client HTTP.
        return error_response(error)

    return success_response(
        count=page["count"],
        limit=page["limit"],
        offset=page["offset"],
        products=page["results"],
    )


async def get_product_details_tool(
    client: ProductAPIClient,
    product_id: int,
) -> dict[str, Any]:
    """Retourne les informations détaillées d'un produit."""

    try:
        product = await client.get_product_details(product_id)

    except MCPClientError as error:
        # L'agent reçoit une erreur structurée plutôt qu'une traceback.
        return error_response(error)

    return success_response(
        product=product,
    )
