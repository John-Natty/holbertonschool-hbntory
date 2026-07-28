"""Contrats publics de la route POST /api/query."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.models.conversation import ConversationId
from app.models.data import (
    NonEmptyString,
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
    StrictModel,
)


QuestionText = Annotated[
    str,
    Field(strict=True),
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=2000,
    ),
]

ErrorCode = Literal[
    "invalid_parameters",
    "resource_not_found",
    "service_timeout",
    "service_unavailable",
    "invalid_service_response",
    "client_error",
    "internal_error",
]


class QueryRequest(StrictModel):
    """Décrit une question publique validée."""

    conversation_id: ConversationId | None = None
    question: QuestionText


class ErrorDetail(StrictModel):
    """Décrit une erreur publique sans détail technique sensible."""

    code: ErrorCode
    message: NonEmptyString


class SuccessResponse(StrictModel):
    """Regroupe les invariants de toutes les réponses réussies."""

    conversation_id: ConversationId
    success: Literal[True] = True
    answer: NonEmptyString
    error: None = None


class ProductListResponse(SuccessResponse):
    """Réponse publique contenant une liste de produits."""

    type: Literal["product_list"] = "product_list"
    data: ProductListData


class ProductDetailsResponse(SuccessResponse):
    """Réponse publique contenant le détail d'un produit."""

    type: Literal["product_details"] = "product_details"
    data: ProductDetailsData


class StockByProductResponse(SuccessResponse):
    """Réponse publique contenant le stock par produit."""

    type: Literal["stock_by_product"] = "stock_by_product"
    data: StockByProductData


class StockByBranchResponse(SuccessResponse):
    """Réponse publique contenant le stock par branche."""

    type: Literal["stock_by_branch"] = "stock_by_branch"
    data: StockByBranchData


class ShoppingListResponse(SuccessResponse):
    """Réponse publique contenant les branches correspondantes."""

    type: Literal["shopping_list"] = "shopping_list"
    data: ShoppingListData


class UnsupportedResponse(SuccessResponse):
    """Refus ou clarification sans affirmation métier structurée."""

    type: Literal["unsupported"] = "unsupported"
    data: None = None


class ErrorResponse(StrictModel):
    """Réponse publique représentant un échec métier prévu."""

    conversation_id: ConversationId
    success: Literal[False] = False
    answer: NonEmptyString
    type: Literal["error"] = "error"
    data: None = None
    error: ErrorDetail


QueryResponse = Annotated[
    ProductListResponse
    | ProductDetailsResponse
    | StockByProductResponse
    | StockByBranchResponse
    | ShoppingListResponse
    | UnsupportedResponse
    | ErrorResponse,
    Field(discriminator="type"),
]
