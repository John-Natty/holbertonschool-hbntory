"""Contrats publics du chargement déterministe du catalogue."""

from typing import Annotated, Literal

from pydantic import Field

from app.models.data import ProductListData, StrictModel
from app.models.query import ErrorDetail


class ProductCatalogSuccessResponse(StrictModel):
    """Retourne une page Produit validée sans texte généré."""

    success: Literal[True] = True
    data: ProductListData
    error: None = None


class ProductCatalogErrorResponse(StrictModel):
    """Retourne une erreur de catalogue sans détail interne."""

    success: Literal[False] = False
    data: None = None
    error: ErrorDetail


ProductCatalogResponse = Annotated[
    ProductCatalogSuccessResponse | ProductCatalogErrorResponse,
    Field(discriminator="success"),
]
