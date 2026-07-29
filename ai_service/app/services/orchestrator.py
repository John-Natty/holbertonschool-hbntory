"""Orchestration conversationnelle unique entre compréhension, MCP et réponse."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Sequence
from typing import Protocol

from app.errors import (
    GeneratedAnswerError,
    MCPClientError,
    MCPConnectionError,
    MCPInvalidArgumentError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPToolResponseError,
)
from app.models.conversation import (
    ConversationObservation,
    ConversationState,
    ReducedBranchStock,
    ReducedMatchingBranch,
    generate_conversation_id,
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
    QueryIntent,
    ShoppingListIntent,
    StockByBranchIntent,
    StockByProductIntent,
    UnsupportedIntent,
)
from app.models.mcp import ShoppingListItem
from app.models.query import (
    ErrorCode,
    ProductListResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.answer_builder import AnswerBuilder
from app.services.answer_generator import BusinessResponse
from app.services.conversation_store import (
    ConversationCapacityError,
    ConversationStore,
)
from app.services.product_page import validate_product_page


logger = logging.getLogger(__name__)
MAX_NATURALIZED_PRODUCT_LIST_ITEMS = 10


class MCPDataClient(Protocol):
    """Contrat des cinq seules lectures métier autorisées."""

    @property
    def is_ready(self) -> bool:
        """Indique si le client peut recevoir un appel."""

        ...

    async def ensure_connected(self) -> bool:
        """Restaure la session de transport sans appel métier."""

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
        """Retourne un produit."""

        ...

    async def get_stock_by_product(
        self,
        product_id: int,
    ) -> StockByProductData:
        """Retourne le stock d'un produit."""

        ...

    async def get_stock_by_branch(
        self,
        branch_id: int | None = None,
        branch_name: str | None = None,
    ) -> StockByBranchData:
        """Retourne le stock d'une branche."""

        ...

    async def check_shopping_list(
        self,
        items: list[ShoppingListItem],
    ) -> ShoppingListData:
        """Retourne les branches satisfaisant une liste."""

        ...


class IntentResolver(Protocol):
    """Contrat du classifieur conversationnel unique."""

    async def resolve(
        self,
        question: str,
        state: ConversationState | None = None,
    ) -> QueryIntent:
        """Retourne une intention strictement validée."""

        ...


class NaturalAnswerGenerator(Protocol):
    """Contrat du générateur naturel unique et facultatif."""

    async def generate(
        self,
        question: str,
        response: BusinessResponse,
        intent: QueryIntent | None = None,
        history: Sequence[object] | None = None,
        state: object | None = None,
    ) -> str:
        """Retourne un texte dont les claims ont été validés."""

        ...


class QueryOrchestrator:
    """Sérialise chaque conversation et exécute au plus un appel MCP."""

    def __init__(
        self,
        intent_classifier: IntentResolver,
        client: MCPDataClient,
        answer_builder: AnswerBuilder,
        answer_generator: NaturalAnswerGenerator | None = None,
        conversation_store: ConversationStore | None = None,
    ) -> None:
        """Injecte une seule chaîne de traitement partagée."""

        self._intent_classifier = intent_classifier
        self._client = client
        self._answer_builder = answer_builder
        self._answer_generator = answer_generator
        self._conversation_store = (
            conversation_store or ConversationStore()
        )

    async def handle(
        self,
        request: QueryRequest | str,
        conversation_id: str | None = None,
        state: ConversationState | None = None,
    ) -> QueryResponse:
        """Traite une requête publique ou un appel direct de compatibilité."""

        if isinstance(request, QueryRequest):
            question = request.question
            requested_id = request.conversation_id
        else:
            question = request
            requested_id = conversation_id

        if state is not None:
            identifier = requested_id or generate_conversation_id()
            response, _observation = await self._execute(
                question,
                identifier,
                state,
            )
            return response

        try:
            async with self._conversation_store.transaction(
                requested_id
            ) as transaction:
                response, observation = await self._execute(
                    question,
                    transaction.conversation_id,
                    transaction.state,
                )

                if observation is not None:
                    transaction.apply(observation)

                transaction.record_turn(question, response.answer)
                return response
        except ConversationCapacityError:
            return self._answer_builder.error(
                "service_unavailable",
                conversation_id=(
                    requested_id or generate_conversation_id()
                ),
            )

    async def _execute(
        self,
        question: str,
        conversation_id: str,
        state: ConversationState,
    ) -> tuple[QueryResponse, ConversationObservation | None]:
        """Résout, effectue une seule lecture, puis réduit l'observation."""

        intent = await self._resolve_intent(question, state)

        if isinstance(intent, UnsupportedIntent):
            return (
                self._answer_builder.unsupported(
                    intent,
                    conversation_id=conversation_id,
                ),
                None,
            )

        if (
            not self._client.is_ready
            and not await self._client.ensure_connected()
        ):
            return (
                self._answer_builder.error(
                    "service_unavailable",
                    conversation_id=conversation_id,
                ),
                None,
            )

        try:
            if isinstance(intent, ProductListIntent):
                data = await self._client.list_products(
                    limit=intent.limit,
                    offset=intent.offset,
                )
                validate_product_page(data, intent.limit, intent.offset)
                response = self._answer_builder.product_list(
                    data,
                    conversation_id=conversation_id,
                )
                observation = ConversationObservation(
                    intent="product_list",
                    product_ids=[
                        product.id
                        for product in data.products[:intent.limit]
                    ],
                )
            elif isinstance(intent, ProductDetailsIntent):
                data = await self._client.get_product_details(
                    intent.product_id
                )
                response = self._answer_builder.product_details(
                    data,
                    conversation_id=conversation_id,
                )
                observation = ConversationObservation(
                    intent="product_details",
                    product_id=data.product.id,
                )
            elif isinstance(intent, StockByProductIntent):
                data = await self._client.get_stock_by_product(
                    intent.product_id
                )
                response = self._answer_builder.stock_by_product(
                    data,
                    intent,
                    conversation_id=conversation_id,
                )
                positive_branches = [
                    branch
                    for branch in data.branches
                    if branch.quantity > 0
                ]
                observed_branch_id = intent.branch_id
                observed_branch_name = intent.branch_name

                if (
                    observed_branch_id is None
                    and observed_branch_name is None
                    and len(positive_branches) == 1
                ):
                    observed_branch_id = positive_branches[0].branch_id
                    observed_branch_name = (
                        positive_branches[0].branch_name
                    )

                observation = ConversationObservation(
                    intent="stock_by_product",
                    product_id=data.product_id,
                    branch_id=observed_branch_id,
                    branch_name=observed_branch_name,
                    stock_branches=[
                        ReducedBranchStock(
                            branch_id=branch.branch_id,
                            branch_name=branch.branch_name,
                            quantity=branch.quantity,
                        )
                        for branch in data.branches
                    ],
                )
            elif isinstance(intent, StockByBranchIntent):
                if intent.branch_id is not None:
                    data = await self._client.get_stock_by_branch(
                        intent.branch_id
                    )
                else:
                    data = await self._client.get_stock_by_branch(
                        branch_name=intent.branch_name
                    )
                response = self._answer_builder.stock_by_branch(
                    data,
                    conversation_id=conversation_id,
                )
                observation = ConversationObservation(
                    intent="stock_by_branch",
                    branch_id=data.branch.id,
                    branch_name=data.branch.name,
                    product_ids=[
                        stock.product_id for stock in data.stocks
                    ],
                )
            elif isinstance(intent, ShoppingListIntent):
                data = await self._client.check_shopping_list(
                    list(intent.items)
                )
                response = self._answer_builder.shopping_list(
                    data,
                    conversation_id=conversation_id,
                )
                observation = ConversationObservation(
                    intent="shopping_list",
                    shopping_items=list(intent.items),
                    matching_branches=[
                        ReducedMatchingBranch(
                            branch_id=branch.branch_id,
                            branch_name=branch.branch_name,
                        )
                        for branch in data.matching_branches
                    ],
                )
            else:
                raise RuntimeError(
                    "Le classifieur a produit une intention inconnue."
                )
        except MCPToolResponseError as error:
            return (
                self._answer_builder.error(
                    _tool_error_code(error.code),
                    conversation_id=conversation_id,
                ),
                None,
            )
        except MCPTimeoutError:
            return (
                self._answer_builder.error(
                    "service_timeout",
                    conversation_id=conversation_id,
                ),
                None,
            )
        except MCPConnectionError:
            return (
                self._answer_builder.error(
                    "service_unavailable",
                    conversation_id=conversation_id,
                ),
                None,
            )
        except MCPInvalidArgumentError:
            return (
                self._answer_builder.error(
                    "invalid_parameters",
                    conversation_id=conversation_id,
                ),
                None,
            )
        except MCPProtocolError:
            return (
                self._answer_builder.error(
                    "invalid_service_response",
                    conversation_id=conversation_id,
                ),
                None,
            )
        except MCPClientError:
            return (
                self._answer_builder.error(
                    "client_error",
                    conversation_id=conversation_id,
                ),
                None,
            )

        return (
            await self._naturalize(
                question,
                response,
                intent,
                state,
            ),
            observation,
        )

    async def _resolve_intent(
        self,
        question: str,
        state: ConversationState,
    ) -> QueryIntent:
        """Supporte les anciens fakes sans masquer un TypeError métier."""

        parameters = inspect.signature(
            self._intent_classifier.resolve
        ).parameters

        if len(parameters) >= 2:
            return await self._intent_classifier.resolve(
                question,
                state,
            )

        return await self._intent_classifier.resolve(  # type: ignore[call-arg]
            question
        )

    async def _naturalize(
        self,
        question: str,
        response: BusinessResponse,
        intent: QueryIntent,
        state: ConversationState,
    ) -> BusinessResponse:
        """Utilise le modèle si ses claims passent, sinon le fallback."""

        if self._answer_generator is None:
            return response

        if (
            isinstance(response, ProductListResponse)
            and len(response.data.products)
            > MAX_NATURALIZED_PRODUCT_LIST_ITEMS
        ):
            return response

        try:
            parameters = inspect.signature(
                self._answer_generator.generate
            ).parameters

            if len(parameters) >= 5:
                answer = await self._answer_generator.generate(
                    question,
                    response,
                    intent,
                    state.turns,
                    state,
                )
            else:
                # Compatibilité des doubles historiques à deux arguments.
                generator = self._answer_generator
                answer = await generator.generate(  # type: ignore[call-arg]
                    question,
                    response,
                )
        except GeneratedAnswerError as error:
            # Le motif du rejet est indispensable pour diagnostiquer un
            # fournisseur qui ne respecte pas le format attendu.
            logger.warning(
                "La réponse naturelle a été remplacée par le fallback : %s",
                error,
            )
            return response

        return response.model_copy(update={"answer": answer})

    async def clear_conversations(self) -> None:
        """Vide la mémoire volatile lors de l'arrêt du processus."""

        await self._conversation_store.clear()


def _tool_error_code(code: str) -> ErrorCode:
    """Convertit un code métier MCP vers le contrat public."""

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
