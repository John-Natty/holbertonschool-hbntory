#!/usr/bin/env python3
"""Serveur MCP HBntory exposant les outils Produit et Stock."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from clients.backoffice_api import BackofficeAPIClient
from clients.product_api import ProductAPIClient
from config import Settings, load_settings
from mcp_compat import enforce_strict_tool_arguments
from schemas import (
    BranchName,
    ListProductsResponse,
    PageLimit,
    PageOffset,
    ProductDetailsResponse,
    ShoppingListItems,
    ShoppingListResponse,
    StockByBranchResponse,
    StockByProductResponse,
    StrictPositiveInt,
)
from tools.product_tools import (
    get_product_details_tool,
    list_products_tool,
)
from tools.stock_tools import (
    check_shopping_list_tool,
    get_stock_by_branch_tool,
    get_stock_by_product_tool,
)


@dataclass(slots=True)
class AppContext:
    """Regroupe les clients HTTP partagés par les outils MCP."""

    product_client: ProductAPIClient
    backoffice_client: BackofficeAPIClient


def create_server(
    settings: Settings | None = None,
) -> FastMCP[AppContext]:
    """Crée et configure le serveur MCP HBntory."""

    resolved_settings = settings or load_settings()

    # Doit être exécuté avant la création des modèles
    # d'arguments générés par les décorateurs MCP.
    enforce_strict_tool_arguments()

    @asynccontextmanager
    async def app_lifespan(
        _server: FastMCP,
    ) -> AsyncIterator[AppContext]:
        """Crée les clients au démarrage et les ferme à l'arrêt."""

        product_client = ProductAPIClient(
            resolved_settings.product_api_base_url,
        )

        backoffice_client = BackofficeAPIClient(
            resolved_settings.backoffice_internal_url,
            resolved_settings.internal_api_key,
        )

        try:
            yield AppContext(
                product_client=product_client,
                backoffice_client=backoffice_client,
            )

        finally:
            await product_client.aclose()
            await backoffice_client.aclose()

    mcp = FastMCP(
        name="HBntory Product MCP",
        instructions=(
            "Consulte le catalogue Produit externe et les stocks "
            "HBntory en lecture seule. N'invente jamais une donnée "
            "absente et retourne les erreurs structurées telles quelles."
        ),
        host=resolved_settings.mcp_host,
        port=resolved_settings.mcp_port,
        streamable_http_path="/mcp",
        json_response=True,
        lifespan=app_lifespan,
    )

    @mcp.tool()
    async def list_products(
        ctx: Context[ServerSession, AppContext],
        limit: PageLimit = 20,
        offset: PageOffset = 0,
    ) -> ListProductsResponse:
        """Liste une page de produits du catalogue externe."""

        app_context = ctx.request_context.lifespan_context

        return await list_products_tool(
            app_context.product_client,
            limit=limit,
            offset=offset,
        )

    @mcp.tool()
    async def get_product_details(
        ctx: Context[ServerSession, AppContext],
        product_id: StrictPositiveInt,
    ) -> ProductDetailsResponse:
        """Retourne les informations détaillées d'un produit."""

        app_context = ctx.request_context.lifespan_context

        return await get_product_details_tool(
            app_context.product_client,
            product_id=product_id,
        )

    @mcp.tool()
    async def get_stock_by_product(
        ctx: Context[ServerSession, AppContext],
        product_id: StrictPositiveInt,
    ) -> StockByProductResponse:
        """Retourne les branches possédant un produit en stock."""

        app_context = ctx.request_context.lifespan_context

        return await get_stock_by_product_tool(
            app_context.backoffice_client,
            product_id=product_id,
        )

    @mcp.tool()
    async def get_stock_by_branch(
        ctx: Context[ServerSession, AppContext],
        branch_id: StrictPositiveInt | None = None,
        branch_name: BranchName | None = None,
    ) -> StockByBranchResponse:
        """Retourne le stock via exactement un identifiant ou un nom."""

        app_context = ctx.request_context.lifespan_context

        return await get_stock_by_branch_tool(
            app_context.backoffice_client,
            app_context.product_client,
            branch_id=branch_id,
            branch_name=branch_name,
        )

    @mcp.tool()
    async def check_shopping_list(
        ctx: Context[ServerSession, AppContext],
        items: ShoppingListItems,
    ) -> ShoppingListResponse:
        """Retourne les branches pouvant satisfaire une liste d'achats."""

        app_context = ctx.request_context.lifespan_context

        serialized_items = [
            item.model_dump()
            for item in items
        ]

        return await check_shopping_list_tool(
            app_context.backoffice_client,
            items=serialized_items,
        )

    return mcp


def main() -> None:
    """Démarre le serveur avec le transport Streamable HTTP."""

    mcp = create_server()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
