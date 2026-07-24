"""Client partagé du serveur MCP Produit et Stock."""

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from datetime import timedelta
from types import TracebackType
from typing import Any, TypeVar

import httpx
from anyio import (
    BrokenResourceError,
    ClosedResourceError,
    EndOfStream,
)
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from pydantic import TypeAdapter, ValidationError

from app.errors import (
    MCPClientError,
    MCPConnectionError,
    MCPInvalidArgumentError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPToolNotFoundError,
    MCPToolResponseError,
)
from app.models.data import (
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
    StrictModel,
)
from app.models.mcp import (
    BranchIdentifierArguments,
    LIST_PRODUCTS_RESULT_ADAPTER,
    ListProductsArguments,
    MCPToolErrorResult,
    PRODUCT_DETAILS_RESULT_ADAPTER,
    ProductIdentifierArguments,
    SHOPPING_LIST_ITEMS_ADAPTER,
    SHOPPING_LIST_RESULT_ADAPTER,
    STOCK_BY_BRANCH_RESULT_ADAPTER,
    STOCK_BY_PRODUCT_RESULT_ADAPTER,
    ShoppingListArguments,
    ShoppingListItem,
)


EXPECTED_TOOLS = frozenset(
    {
        "list_products",
        "get_product_details",
        "get_stock_by_product",
        "get_stock_by_branch",
        "check_shopping_list",
    }
)

TransportContext = AbstractAsyncContextManager[
    tuple[Any, Any, Callable[[], str | None]]
]
TransportFactory = Callable[..., TransportContext]
SessionFactory = Callable[..., AbstractAsyncContextManager[ClientSession]]
ResultModel = TypeVar("ResultModel", bound=StrictModel)

_TRANSPORT_ERRORS = (
    httpx.HTTPError,
    BrokenResourceError,
    ClosedResourceError,
    EndOfStream,
)


class ProductMCPClient:
    """Maintient une seule session MCP Streamable HTTP partagée."""

    def __init__(
        self,
        server_url: str,
        request_timeout_seconds: float,
        max_concurrent_calls: int,
        *,
        transport_factory: TransportFactory = streamable_http_client,
        session_factory: SessionFactory = ClientSession,
    ) -> None:
        """Injecte la configuration et les fabriques du transport."""

        self._server_url = server_url
        self._request_timeout_seconds = request_timeout_seconds
        self._transport_factory = transport_factory
        self._session_factory = session_factory
        self._semaphore = asyncio.Semaphore(max_concurrent_calls)
        self._lifecycle_lock = asyncio.Lock()
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    @property
    def is_ready(self) -> bool:
        """Indique si la session a validé les cinq outils attendus."""

        return self._session is not None and self._stack is not None

    async def __aenter__(self) -> "ProductMCPClient":
        """Connecte le client à l'entrée du contexte."""

        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Ferme le client à la sortie du contexte."""

        await self.close()

    async def connect(self) -> None:
        """Ouvre et initialise une session MCP de manière idempotente."""

        async with self._lifecycle_lock:
            if self.is_ready:
                return

            stack = AsyncExitStack()

            try:
                transport = await stack.enter_async_context(
                    self._transport_factory(self._server_url)
                )
                read_stream, write_stream, _ = transport
                session = await stack.enter_async_context(
                    self._session_factory(
                        read_stream,
                        write_stream,
                        read_timeout_seconds=timedelta(
                            seconds=self._request_timeout_seconds
                        ),
                    )
                )

                async with asyncio.timeout(
                    self._request_timeout_seconds
                ):
                    await session.initialize()
                    tools_result = await session.list_tools()

                self._validate_tools(tools_result)
            except BaseException as error:
                await self._close_failed_stack(stack)
                translated = self._translate_expected_error(
                    error,
                    during_connection=True,
                )

                if translated is not None:
                    raise translated from error

                raise

            self._stack = stack
            self._session = session

    async def close(self) -> None:
        """Ferme les ressources MCP de manière idempotente."""

        async with self._lifecycle_lock:
            stack = self._stack
            self._stack = None
            self._session = None

            if stack is None:
                return

            try:
                await stack.aclose()
            except BaseException as error:
                translated = self._translate_expected_error(
                    error,
                    during_connection=True,
                )

                if translated is not None:
                    raise translated from error

                raise

    async def list_products(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> ProductListData:
        """Retourne une page Produit validée."""

        arguments = self._validate_arguments(
            ListProductsArguments,
            {
                "limit": limit,
                "offset": offset,
            },
        )
        result = await self._call_and_validate(
            "list_products",
            arguments.model_dump(),
            LIST_PRODUCTS_RESULT_ADAPTER,
            ProductListData,
        )

        return result

    async def get_product_details(
        self,
        product_id: int,
    ) -> ProductDetailsData:
        """Retourne le détail validé d'un produit."""

        arguments = self._validate_arguments(
            ProductIdentifierArguments,
            {
                "product_id": product_id,
            },
        )

        return await self._call_and_validate(
            "get_product_details",
            arguments.model_dump(),
            PRODUCT_DETAILS_RESULT_ADAPTER,
            ProductDetailsData,
        )

    async def get_stock_by_product(
        self,
        product_id: int,
    ) -> StockByProductData:
        """Retourne les stocks validés d'un produit."""

        arguments = self._validate_arguments(
            ProductIdentifierArguments,
            {
                "product_id": product_id,
            },
        )

        return await self._call_and_validate(
            "get_stock_by_product",
            arguments.model_dump(),
            STOCK_BY_PRODUCT_RESULT_ADAPTER,
            StockByProductData,
        )

    async def get_stock_by_branch(
        self,
        branch_id: int,
    ) -> StockByBranchData:
        """Retourne les stocks validés d'une branche."""

        arguments = self._validate_arguments(
            BranchIdentifierArguments,
            {
                "branch_id": branch_id,
            },
        )

        return await self._call_and_validate(
            "get_stock_by_branch",
            arguments.model_dump(),
            STOCK_BY_BRANCH_RESULT_ADAPTER,
            StockByBranchData,
        )

    async def check_shopping_list(
        self,
        items: list[ShoppingListItem],
    ) -> ShoppingListData:
        """Retourne les branches satisfaisant la liste validée."""

        try:
            validated_items = SHOPPING_LIST_ITEMS_ADAPTER.validate_python(
                items
            )
            arguments = ShoppingListArguments(items=validated_items)
        except ValidationError as error:
            raise MCPInvalidArgumentError(
                "La liste d'achats est invalide."
            ) from error

        return await self._call_and_validate(
            "check_shopping_list",
            arguments.model_dump(),
            SHOPPING_LIST_RESULT_ADAPTER,
            ShoppingListData,
        )

    async def _call_and_validate(
        self,
        tool_name: str,
        arguments: dict[str, object],
        adapter: TypeAdapter[Any],
        data_model: type[ResultModel],
    ) -> ResultModel:
        """Valide l'enveloppe métier et retourne les données utiles."""

        raw_result = await self._call_tool(tool_name, arguments)

        if type(raw_result.get("success")) is not bool:
            raise MCPProtocolError(
                "L'indicateur de réussite MCP est invalide."
            )

        try:
            result = adapter.validate_python(raw_result)
        except ValidationError as error:
            raise MCPProtocolError(
                "La réponse métier MCP est invalide."
            ) from error

        if isinstance(result, MCPToolErrorResult):
            raise MCPToolResponseError(
                tool_name=tool_name,
                code=result.error.code,
            )

        try:
            return data_model.model_validate(
                result.model_dump(
                    mode="json",
                    exclude={
                        "success",
                        "error",
                    },
                )
            )
        except ValidationError as error:
            raise MCPProtocolError(
                "Les données métier MCP sont invalides."
            ) from error

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        """Appelle un outil autorisé et vérifie son enveloppe MCP."""

        session = self._session

        if session is None or not self.is_ready:
            raise MCPConnectionError(
                "Le serveur MCP n'est pas connecté."
            )

        if tool_name not in EXPECTED_TOOLS:
            raise MCPToolNotFoundError(
                "L'outil MCP demandé n'est pas autorisé."
            )

        try:
            async with self._semaphore:
                async with asyncio.timeout(
                    self._request_timeout_seconds
                ):
                    tool_result = await session.call_tool(
                        tool_name,
                        arguments,
                        read_timeout_seconds=timedelta(
                            seconds=self._request_timeout_seconds
                        ),
                    )
        except BaseException as error:
            translated = self._translate_expected_error(
                error,
                during_connection=False,
            )

            if translated is not None:
                raise translated from error

            raise

        if getattr(tool_result, "isError", None) is not False:
            raise MCPProtocolError(
                "L'outil MCP a signalé une erreur protocolaire."
            )

        structured_content = getattr(
            tool_result,
            "structuredContent",
            None,
        )

        if not isinstance(structured_content, dict):
            raise MCPProtocolError(
                "Le contenu structuré MCP est absent ou invalide."
            )

        if set(structured_content) != {"result"}:
            raise MCPProtocolError(
                "L'enveloppe structurée MCP est invalide."
            )

        result = structured_content["result"]

        if not isinstance(result, dict):
            raise MCPProtocolError(
                "Le résultat structuré MCP est invalide."
            )

        return result

    @staticmethod
    def _validate_arguments(
        model: type[ResultModel],
        values: dict[str, object],
    ) -> ResultModel:
        """Transforme une erreur Pydantic en erreur locale contrôlée."""

        try:
            return model.model_validate(values)
        except ValidationError as error:
            raise MCPInvalidArgumentError(
                "Les arguments de l'outil MCP sont invalides."
            ) from error

    @staticmethod
    def _validate_tools(tools_result: object) -> None:
        """Exige exactement les cinq outils, sans nom dupliqué."""

        tools = getattr(tools_result, "tools", None)
        next_cursor = getattr(tools_result, "nextCursor", None)

        if next_cursor is not None:
            raise MCPProtocolError(
                "La liste des outils MCP est paginée."
            )

        if not isinstance(tools, list):
            raise MCPProtocolError(
                "La liste des outils MCP est invalide."
            )

        names: list[str] = []

        for tool in tools:
            name = getattr(tool, "name", None)

            if not isinstance(name, str) or not name.strip():
                raise MCPProtocolError(
                    "Un nom d'outil MCP est invalide."
                )

            names.append(name)

        if len(names) != len(set(names)):
            raise MCPProtocolError(
                "La liste des outils MCP contient un doublon."
            )

        actual_tools = set(names)
        unexpected_tools = actual_tools - EXPECTED_TOOLS
        missing_tools = EXPECTED_TOOLS - actual_tools

        if unexpected_tools:
            raise MCPProtocolError(
                "La liste des outils MCP contient un outil inattendu."
            )

        if missing_tools:
            raise MCPToolNotFoundError(
                "Un outil MCP obligatoire est absent."
            )

    @staticmethod
    async def _close_failed_stack(stack: AsyncExitStack) -> None:
        """Ferme les ressources créées avant un échec de connexion."""

        try:
            await stack.aclose()
        except BaseException as error:
            translated = ProductMCPClient._translate_expected_error(
                error,
                during_connection=True,
            )

            if translated is None:
                raise

    @staticmethod
    def _translate_expected_error(
        error: BaseException,
        *,
        during_connection: bool,
    ) -> MCPClientError | None:
        """Traduit uniquement les erreurs attendues du SDK et du transport."""

        if isinstance(error, MCPClientError):
            return error

        if isinstance(error, (TimeoutError, httpx.TimeoutException)):
            return MCPTimeoutError(
                "Le délai de réponse du serveur MCP est dépassé."
            )

        if isinstance(error, McpError):
            if error.error.code == 408:
                return MCPTimeoutError(
                    "Le délai de réponse du serveur MCP est dépassé."
                )

            if during_connection:
                return MCPConnectionError(
                    "La connexion au serveur MCP a échoué."
                )

            return MCPProtocolError(
                "L'échange avec le serveur MCP a échoué."
            )

        if isinstance(error, _TRANSPORT_ERRORS):
            return MCPConnectionError(
                "La connexion au serveur MCP a échoué."
            )

        if isinstance(error, BaseExceptionGroup):
            translated_errors = [
                ProductMCPClient._translate_expected_error(
                    nested_error,
                    during_connection=during_connection,
                )
                for nested_error in error.exceptions
            ]

            if any(
                translated_error is None
                for translated_error in translated_errors
            ):
                return None

            if all(
                isinstance(translated_error, MCPTimeoutError)
                for translated_error in translated_errors
            ):
                return MCPTimeoutError(
                    "Le délai de réponse du serveur MCP est dépassé."
                )

            return MCPConnectionError(
                "La connexion au serveur MCP a échoué."
            )

        return None
