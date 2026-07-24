#!/usr/bin/env python3
"""Schémas d'entrée et de sortie des outils MCP HBntory."""

from datetime import datetime
from typing import Annotated, Any, Literal

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

PageOffset = StrictNonNegativeInt

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

NonEmptyString = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]


def _require_datetime_string(value: Any) -> Any:
    """Refuse toute conversion implicite d'un nombre en date."""

    if not isinstance(value, str):
        raise ValueError(
            "La date doit être fournie sous forme de chaîne ISO 8601."
        )

    return value


ISODateTimeString = Annotated[
    datetime,
    BeforeValidator(_require_datetime_string),
]


class StrictSchema(BaseModel):
    """Modèle rejetant tous les champs JSON inattendus."""

    model_config = ConfigDict(
        extra="forbid",
    )


class ShoppingListItemInput(StrictSchema):
    """Décrit un produit et sa quantité dans une liste d'achats."""

    product_id: StrictPositiveInt
    quantity: StrictPositiveInt


ShoppingListItems = Annotated[
    list[ShoppingListItemInput],
    Field(min_length=1),
]


class SupplierSchema(StrictSchema):
    """Décrit le fournisseur détaillé d'un produit."""

    id: NonEmptyString
    name: NonEmptyString
    contact_email: NonEmptyString
    country: NonEmptyString
    lead_time_days: StrictNonNegativeInt
    reliability_score: StrictFiniteFloat


class ProductSchema(StrictSchema):
    """Décrit les métadonnées officielles d'un produit."""

    id: StrictPositiveInt
    sku: NonEmptyString
    name: NonEmptyString
    description: str
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
    supplier: SupplierSchema | None = None


class ProductBranchSchema(StrictSchema):
    """Décrit le stock d'un produit dans une branche."""

    branch_id: StrictPositiveInt
    branch_name: NonEmptyString
    quantity: StrictNonNegativeInt


class BranchSchema(StrictSchema):
    """Décrit une branche HBntory."""

    id: StrictPositiveInt
    name: NonEmptyString


class StockSchema(StrictSchema):
    """Décrit une quantité locale associée à un produit."""

    product_id: StrictPositiveInt
    quantity: StrictNonNegativeInt


class MatchingItemSchema(StrictSchema):
    """Décrit un produit satisfait par une branche."""

    product_id: StrictPositiveInt
    requested_quantity: StrictPositiveInt
    available_quantity: StrictNonNegativeInt


class MatchingBranchSchema(StrictSchema):
    """Décrit une branche satisfaisant toute la liste d'achats."""

    branch_id: StrictPositiveInt
    branch_name: NonEmptyString
    items: list[MatchingItemSchema]


ToolErrorCode = Literal[
    "invalid_parameters",
    "resource_not_found",
    "service_timeout",
    "service_unavailable",
    "invalid_service_response",
    "client_error",
]


class ToolErrorSchema(StrictSchema):
    """Décrit une erreur publique retournée par un outil MCP."""

    code: ToolErrorCode
    message: NonEmptyString


class ToolErrorResponse(StrictSchema):
    """Décrit l'échec structuré d'un outil MCP."""

    success: Literal[False]
    error: ToolErrorSchema


class ListProductsSuccess(StrictSchema):
    """Décrit le résultat réussi de list_products."""

    success: Literal[True]
    count: StrictNonNegativeInt
    limit: PageLimit
    offset: PageOffset
    products: list[ProductSchema]
    error: None = None


class ProductDetailsSuccess(StrictSchema):
    """Décrit le résultat réussi de get_product_details."""

    success: Literal[True]
    product: ProductSchema
    error: None = None


class StockByProductSuccess(StrictSchema):
    """Décrit le résultat réussi de get_stock_by_product."""

    success: Literal[True]
    product_id: StrictPositiveInt
    branches: list[ProductBranchSchema]
    error: None = None


class StockByBranchSuccess(StrictSchema):
    """Décrit le résultat réussi de get_stock_by_branch."""

    success: Literal[True]
    branch: BranchSchema
    stocks: list[StockSchema]
    error: None = None


class ShoppingListSuccess(StrictSchema):
    """Décrit le résultat réussi de check_shopping_list."""

    success: Literal[True]
    matching_branches: list[MatchingBranchSchema]
    error: None = None


ListProductsResponse = Annotated[
    ListProductsSuccess | ToolErrorResponse,
    Field(discriminator="success"),
]

ProductDetailsResponse = Annotated[
    ProductDetailsSuccess | ToolErrorResponse,
    Field(discriminator="success"),
]

StockByProductResponse = Annotated[
    StockByProductSuccess | ToolErrorResponse,
    Field(discriminator="success"),
]

StockByBranchResponse = Annotated[
    StockByBranchSuccess | ToolErrorResponse,
    Field(discriminator="success"),
]

ShoppingListResponse = Annotated[
    ShoppingListSuccess | ToolErrorResponse,
    Field(discriminator="success"),
]
