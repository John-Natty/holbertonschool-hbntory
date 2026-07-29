"""Modèles stricts des intentions comprises par le service IA."""

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.models.data import (
    BranchName,
    NonEmptyString,
    PageLimit,
    StrictModel,
    StrictNonNegativeInt,
    StrictPositiveInt,
)
from app.models.mcp import ShoppingListItem, ShoppingListItems


UnsupportedReason = Literal[
    "out_of_domain",
    "missing_product_id",
    "missing_branch_id",
    "missing_items",
    "read_only",
    "ambiguous",
    "unrecognized",
]


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
    """Demande le stock d'un produit, éventuellement dans une branche."""

    type: Literal["stock_by_product"] = "stock_by_product"
    product_id: StrictPositiveInt
    branch_id: StrictPositiveInt | None = None
    branch_name: BranchName | None = None

    @field_validator("branch_name", mode="before")
    @classmethod
    def normalize_branch_name(cls, value):
        """Normalise les espaces sans changer le nom métier."""

        if isinstance(value, str):
            return " ".join(value.split())

        return value

    @model_validator(mode="after")
    def allow_at_most_one_branch_reference(self):
        """Refuse deux références concurrentes de la même branche."""

        if self.branch_id is not None and self.branch_name is not None:
            raise ValueError(
                "Une seule référence de branche peut être fournie."
            )

        return self


class StockByBranchIntent(StrictModel):
    """Demande le contenu d'une branche identifiée."""

    type: Literal["stock_by_branch"] = "stock_by_branch"
    branch_id: StrictPositiveInt | None = None
    branch_name: BranchName | None = None

    @field_validator("branch_name", mode="before")
    @classmethod
    def normalize_branch_name(cls, value):
        """Normalise les espaces sans changer le nom métier."""

        if isinstance(value, str):
            return " ".join(value.split())

        return value

    @model_validator(mode="after")
    def require_exactly_one_branch_reference(self):
        """Exige soit un identifiant, soit un nom de branche."""

        if (self.branch_id is None) == (self.branch_name is None):
            raise ValueError(
                "Une seule référence de branche doit être fournie."
            )

        return self


class ShoppingListIntent(StrictModel):
    """Demande les branches satisfaisant une liste explicite."""

    type: Literal["shopping_list"] = "shopping_list"
    items: ShoppingListItems

    @field_validator("items")
    @classmethod
    def normalize_duplicate_products(cls, value):
        """Additionne les doublons en conservant leur premier ordre."""

        if len(value) > 100:
            raise ValueError(
                "Une liste d’achats ne peut pas dépasser 100 lignes."
            )

        quantities: dict[int, int] = {}

        for item in value:
            quantities[item.product_id] = (
                quantities.get(item.product_id, 0) + item.quantity
            )

        return [
            ShoppingListItem(
                product_id=product_id,
                quantity=quantity,
            )
            for product_id, quantity in quantities.items()
        ]


class UnsupportedIntent(StrictModel):
    """Signale une question insuffisamment explicite."""

    type: Literal["unsupported"] = "unsupported"
    reason_code: UnsupportedReason = "unrecognized"
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
