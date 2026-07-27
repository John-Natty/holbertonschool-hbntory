"""Modèles stricts des intentions comprises par le service IA."""

from typing import Annotated, Literal

from pydantic import Field

from app.models.data import (
    NonEmptyString,
    PageLimit,
    StrictModel,
    StrictNonNegativeInt,
    StrictPositiveInt,
)
from app.models.mcp import ShoppingListItems


class ProductListIntent(StrictModel):
    """Demande une page du catalogue Produit."""

    type: Literal["product_list"] = "product_list"
    limit: PageLimit = 20
    offset: StrictNonNegativeInt = 0


class ProductDetailsIntent(StrictModel):
    """Demande le détail d'un produit identifié."""

    type: Literal["product_details"] = "product_details"
    product_id: StrictPositiveInt


class StockByProductIntent(StrictModel):
    """Demande les branches possédant un produit identifié."""

    type: Literal["stock_by_product"] = "stock_by_product"
    product_id: StrictPositiveInt


class StockByBranchIntent(StrictModel):
    """Demande le contenu d'une branche identifiée."""

    type: Literal["stock_by_branch"] = "stock_by_branch"
    branch_id: StrictPositiveInt


class ShoppingListIntent(StrictModel):
    """Demande les branches satisfaisant une liste explicite."""

    type: Literal["shopping_list"] = "shopping_list"
    items: ShoppingListItems


class UnsupportedIntent(StrictModel):
    """Signale une question insuffisamment explicite."""

    type: Literal["unsupported"] = "unsupported"
    reason: NonEmptyString


QueryIntent = Annotated[
    ProductListIntent
    | ProductDetailsIntent
    | StockByProductIntent
    | StockByBranchIntent
    | ShoppingListIntent
    | UnsupportedIntent,
    Field(discriminator="type"),
]
