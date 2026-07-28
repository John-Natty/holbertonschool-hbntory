"""Validation de cohérence d'une page Produit reçue du MCP."""

from app.errors import MCPProtocolError
from app.models.data import ProductListData


def validate_product_page(
    data: ProductListData,
    requested_limit: int,
    requested_offset: int,
) -> None:
    """Exige que la pagination MCP respecte exactement la demande."""

    if (
        data.limit != requested_limit
        or data.offset != requested_offset
        or len(data.products) > requested_limit
        or data.count < len(data.products)
    ):
        raise MCPProtocolError(
            "La pagination MCP ne correspond pas à la demande."
        )
