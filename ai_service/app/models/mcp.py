"""Contrats stricts des échanges avec les cinq outils MCP."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, TypeAdapter

from app.models.data import (
    PageLimit,
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
    StrictModel,
    StrictNonNegativeInt,
    StrictPositiveInt,
)


class ShoppingListItem(StrictModel):
    """Décrit un article demandé à check_shopping_list."""

    product_id: StrictPositiveInt
    quantity: StrictPositiveInt


ShoppingListItems = Annotated[
    list[ShoppingListItem],
    Field(strict=True, min_length=1),
]


class ListProductsArguments(StrictModel):
    """Valide les paramètres de pagination de list_products."""

    limit: PageLimit = 20
    offset: StrictNonNegativeInt = 0


class ProductIdentifierArguments(StrictModel):
    """Valide un identifiant Produit avant l'appel MCP."""

    product_id: StrictPositiveInt


class BranchIdentifierArguments(StrictModel):
    """Valide un identifiant de branche avant l'appel MCP."""

    branch_id: StrictPositiveInt


class ShoppingListArguments(StrictModel):
    """Valide une liste d'achats avant l'appel MCP."""

    items: ShoppingListItems


ToolErrorCode = Literal[
    "invalid_parameters",
    "resource_not_found",
    "service_timeout",
    "service_unavailable",
    "invalid_service_response",
    "client_error",
]


class MCPToolErrorDetail(StrictModel):
    """Décrit l'erreur métier sûre d'un outil MCP."""

    code: ToolErrorCode
    message: Annotated[
        str,
        Field(strict=True),
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
        ),
    ]


class MCPToolErrorResult(StrictModel):
    """Décrit un résultat métier MCP en échec."""

    success: Literal[False]
    error: MCPToolErrorDetail


class MCPListProductsSuccess(ProductListData):
    """Décrit un résultat réussi de list_products."""

    success: Literal[True]
    error: None = None


class MCPProductDetailsSuccess(ProductDetailsData):
    """Décrit un résultat réussi de get_product_details."""

    success: Literal[True]
    error: None = None


class MCPStockByProductSuccess(StockByProductData):
    """Décrit un résultat réussi de get_stock_by_product."""

    success: Literal[True]
    error: None = None


class MCPStockByBranchSuccess(StockByBranchData):
    """Décrit un résultat réussi de get_stock_by_branch."""

    success: Literal[True]
    error: None = None


class MCPShoppingListSuccess(ShoppingListData):
    """Décrit un résultat réussi de check_shopping_list."""

    success: Literal[True]
    error: None = None


ListProductsResult = Annotated[
    MCPListProductsSuccess | MCPToolErrorResult,
    Field(discriminator="success"),
]

ProductDetailsResult = Annotated[
    MCPProductDetailsSuccess | MCPToolErrorResult,
    Field(discriminator="success"),
]

StockByProductResult = Annotated[
    MCPStockByProductSuccess | MCPToolErrorResult,
    Field(discriminator="success"),
]

StockByBranchResult = Annotated[
    MCPStockByBranchSuccess | MCPToolErrorResult,
    Field(discriminator="success"),
]

ShoppingListResult = Annotated[
    MCPShoppingListSuccess | MCPToolErrorResult,
    Field(discriminator="success"),
]


SHOPPING_LIST_ITEMS_ADAPTER = TypeAdapter(ShoppingListItems)
LIST_PRODUCTS_RESULT_ADAPTER = TypeAdapter(ListProductsResult)
PRODUCT_DETAILS_RESULT_ADAPTER = TypeAdapter(ProductDetailsResult)
STOCK_BY_PRODUCT_RESULT_ADAPTER = TypeAdapter(StockByProductResult)
STOCK_BY_BRANCH_RESULT_ADAPTER = TypeAdapter(StockByBranchResult)
SHOPPING_LIST_RESULT_ADAPTER = TypeAdapter(ShoppingListResult)
