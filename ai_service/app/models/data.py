"""Modèles locaux reflétant les données utiles des outils MCP."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
)


StrictPositiveInt = Annotated[
    int,
    Field(strict=True, gt=0),
]

StrictNonNegativeInt = Annotated[
    int,
    Field(strict=True, ge=0),
]

PageLimit = Annotated[
    int,
    Field(strict=True, ge=1, le=100),
]

NonNegativeFiniteFloat = Annotated[
    float,
    Field(
        strict=True,
        ge=0,
        allow_inf_nan=False,
    ),
]

StrictFiniteFloat = Annotated[
    float,
    Field(
        strict=True,
        allow_inf_nan=False,
    ),
]

StrictString = Annotated[
    str,
    Field(strict=True),
]

NonEmptyString = Annotated[
    str,
    Field(strict=True),
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]

BranchName = Annotated[
    str,
    Field(strict=True),
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
    ),
]


def _require_datetime_string(value: Any) -> Any:
    """Refuse la conversion implicite d'un nombre en date."""

    if not isinstance(value, str):
        raise ValueError(
            "La date doit être fournie sous forme de chaîne ISO 8601."
        )

    return value


ISODateTimeString = Annotated[
    datetime,
    BeforeValidator(_require_datetime_string),
]


class StrictModel(BaseModel):
    """Modèle de base refusant tous les champs supplémentaires."""

    model_config = ConfigDict(extra="forbid")


class SupplierData(StrictModel):
    """Décrit le fournisseur détaillé d'un produit."""

    id: NonEmptyString
    name: NonEmptyString
    contact_email: NonEmptyString
    country: NonEmptyString
    lead_time_days: StrictNonNegativeInt
    reliability_score: StrictFiniteFloat


class ProductData(StrictModel):
    """Décrit les données Produit reçues par le serveur MCP."""

    id: StrictPositiveInt
    sku: NonEmptyString
    name: NonEmptyString
    description: StrictString
    category: NonEmptyString
    brand: NonEmptyString
    supplier_id: NonEmptyString
    supplier_name: NonEmptyString
    unit_price: NonNegativeFiniteFloat
    currency: NonEmptyString
    discontinued: StrictBool
    weight_kg: NonNegativeFiniteFloat
    tags: list[NonEmptyString]
    updated_at: ISODateTimeString
    supplier: SupplierData | None = None


class ProductBranchData(StrictModel):
    """Décrit le stock d'un produit dans une branche."""

    branch_id: StrictPositiveInt
    branch_name: NonEmptyString
    quantity: StrictNonNegativeInt


class BranchData(StrictModel):
    """Décrit une branche HBntory."""

    id: StrictPositiveInt
    name: NonEmptyString


class StockData(StrictModel):
    """Décrit un produit tarifé et sa quantité dans une branche."""

    product_id: StrictPositiveInt
    product_name: NonEmptyString
    unit_price: NonNegativeFiniteFloat
    currency: NonEmptyString
    quantity: StrictNonNegativeInt


class MatchingItemData(StrictModel):
    """Décrit un produit satisfait par une branche."""

    product_id: StrictPositiveInt
    requested_quantity: StrictPositiveInt
    available_quantity: StrictNonNegativeInt


class MatchingBranchData(StrictModel):
    """Décrit une branche satisfaisant une liste d'achats."""

    branch_id: StrictPositiveInt
    branch_name: NonEmptyString
    items: list[MatchingItemData]


class ProductListData(StrictModel):
    """Décrit les données utiles retournées par list_products."""

    count: StrictNonNegativeInt
    limit: PageLimit
    offset: StrictNonNegativeInt
    products: list[ProductData]


class ProductDetailsData(StrictModel):
    """Décrit les données utiles de get_product_details."""

    product: ProductData


class StockByProductData(StrictModel):
    """Décrit les données utiles de get_stock_by_product."""

    product_id: StrictPositiveInt
    branches: list[ProductBranchData]


class StockByBranchData(StrictModel):
    """Décrit les données utiles de get_stock_by_branch."""

    branch: BranchData
    stocks: list[StockData]


class ShoppingListData(StrictModel):
    """Décrit les données utiles de check_shopping_list."""

    matching_branches: list[MatchingBranchData]
