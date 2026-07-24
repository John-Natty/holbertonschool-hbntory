"""Orchestration déterministe entre les intentions et le client MCP."""

from typing import Protocol

from app.errors import (
    MCPClientError,
    MCPConnectionError,
    MCPInvalidArgumentError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPToolResponseError,
)
from app.models.data import (
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
)
from app.models.intents import (
    ProductDetailsIntent,
    ProductListIntent,
    ShoppingListIntent,
    StockByBranchIntent,
    StockByProductIntent,
    UnsupportedIntent,
)
from app.models.mcp import ShoppingListItem
from app.models.query import ErrorCode, QueryResponse
from app.services.answer_builder import AnswerBuilder
from app.services.intent_router import IntentRouter


class MCPDataClient(Protocol):
    """Contrat minimal du client de données utilisé par l'orchestrateur."""

    @property
    def is_ready(self) -> bool:
        """Indique si le client peut recevoir un appel."""

        ...

    async def list_products(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> ProductListData:
        """Retourne une page Produit."""

        ...

    async def get_product_details(
        self,
        product_id: int,
    ) -> ProductDetailsData:
        """Retourne le détail d'un produit."""

        ...

    async def get_stock_by_product(
        self,
        product_id: int,
    ) -> StockByProductData:
        """Retourne les stocks associés à un produit."""

        ...

    async def get_stock_by_branch(
        self,
        branch_id: int,
    ) -> StockByBranchData:
        """Retourne les stocks associés à une branche."""

        ...

    async def check_shopping_list(
        self,
        items: list[ShoppingListItem],
    ) -> ShoppingListData:
        """Retourne les branches satisfaisant une liste."""

        ...


class QueryOrchestrator:
    """Exécute au maximum un appel MCP pour une question."""

    def __init__(
        self,
        intent_router: IntentRouter,
        client: MCPDataClient,
        answer_builder: AnswerBuilder,
    ) -> None:
        """Injecte les trois collaborateurs de l'orchestration."""

        self._intent_router = intent_router
        self._client = client
        self._answer_builder = answer_builder

    async def handle(
        self,
        question: str,
    ) -> QueryResponse:
        """Route une question, appelle un outil et construit la réponse."""

        if not self._client.is_ready:
            return self._answer_builder.error(
                "service_unavailable"
            )

        intent = await self._intent_router.resolve(question)

        if isinstance(intent, UnsupportedIntent):
            return self._answer_builder.unsupported()

        try:
            if isinstance(intent, ProductListIntent):
                data = await self._client.list_products(
                    limit=intent.limit,
                    offset=intent.offset,
                )
                return self._answer_builder.product_list(data)

            if isinstance(intent, ProductDetailsIntent):
                data = await self._client.get_product_details(
                    intent.product_id
                )
                return self._answer_builder.product_details(data)

            if isinstance(intent, StockByProductIntent):
                data = await self._client.get_stock_by_product(
                    intent.product_id
                )
                return self._answer_builder.stock_by_product(data)

            if isinstance(intent, StockByBranchIntent):
                data = await self._client.get_stock_by_branch(
                    intent.branch_id
                )
                return self._answer_builder.stock_by_branch(data)

            if isinstance(intent, ShoppingListIntent):
                data = await self._client.check_shopping_list(
                    intent.items
                )
                return self._answer_builder.shopping_list(data)
        except MCPToolResponseError as error:
            return self._answer_builder.error(
                _tool_error_code(error.code)
            )
        except MCPTimeoutError:
            return self._answer_builder.error("service_timeout")
        except MCPConnectionError:
            return self._answer_builder.error(
                "service_unavailable"
            )
        except MCPInvalidArgumentError:
            return self._answer_builder.error(
                "invalid_parameters"
            )
        except MCPProtocolError:
            return self._answer_builder.error(
                "invalid_service_response"
            )
        except MCPClientError:
            return self._answer_builder.error("client_error")

        raise RuntimeError(
            "Le routeur a produit une intention non prise en charge."
        )


def _tool_error_code(code: str) -> ErrorCode:
    """Convertit un code métier MCP vers le contrat REST existant."""

    mappings: dict[str, ErrorCode] = {
        "product_not_found": "resource_not_found",
        "branch_not_found": "resource_not_found",
        "resource_not_found": "resource_not_found",
        "invalid_parameters": "invalid_parameters",
        "service_timeout": "service_timeout",
        "service_unavailable": "service_unavailable",
        "invalid_service_response": "invalid_service_response",
        "client_error": "client_error",
    }

    return mappings.get(code, "client_error")
