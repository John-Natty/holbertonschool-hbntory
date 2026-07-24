"""Tests de l'orchestrateur déterministe et de ses réponses."""

import pytest

from app.errors import (
    MCPClientError,
    MCPConnectionError,
    MCPInvalidArgumentError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPToolResponseError,
)
from app.models.data import (
    BranchData,
    ProductData,
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
from app.models.query import ErrorResponse
from app.services.answer_builder import AnswerBuilder
from app.services.orchestrator import QueryOrchestrator


pytestmark = pytest.mark.asyncio


def product_data() -> ProductData:
    """Construit un produit validé commun aux tests."""

    return ProductData(
        id=12,
        sku="HB-TEST-0012",
        name="Produit de test",
        description="Description.",
        category="Tests",
        brand="HBntory",
        supplier_id="SUP-001",
        supplier_name="Fournisseur",
        unit_price=19.99,
        currency="EUR",
        discontinued=False,
        weight_kg=1.25,
        tags=["test"],
        updated_at="2026-07-24T12:00:00Z",
        supplier=None,
    )


class FakeIntentRouter:
    """Retourne une intention prédéfinie et enregistre la question."""

    def __init__(self, intent: QueryIntent) -> None:
        """Conserve l'intention à retourner."""

        self.intent = intent
        self.questions: list[str] = []

    async def resolve(self, question: str) -> QueryIntent:
        """Retourne l'intention sans analyser la question."""

        self.questions.append(question)
        return self.intent


class FakeMCPDataClient:
    """Faux client typé enregistrant chaque méthode appelée."""

    def __init__(self) -> None:
        """Prépare des résultats valides et une éventuelle erreur."""

        self.ready = True
        self.calls: list[tuple[str, object]] = []
        self.error: Exception | None = None
        self.products = ProductListData(
            count=1,
            limit=10,
            offset=5,
            products=[product_data()],
        )
        self.details = ProductDetailsData(
            product=product_data()
        )
        self.by_product = StockByProductData(
            product_id=12,
            branches=[
                {
                    "branch_id": 1,
                    "branch_name": "Toulouse",
                    "quantity": 8,
                }
            ],
        )
        self.by_branch = StockByBranchData(
            branch=BranchData(
                id=3,
                name="Carcassonne",
            ),
            stocks=[
                {
                    "product_id": 12,
                    "quantity": 8,
                }
            ],
        )
        self.shopping = ShoppingListData(
            matching_branches=[
                {
                    "branch_id": 1,
                    "branch_name": "Toulouse",
                    "items": [
                        {
                            "product_id": 12,
                            "requested_quantity": 2,
                            "available_quantity": 8,
                        }
                    ],
                }
            ]
        )

    @property
    def is_ready(self) -> bool:
        """Expose la disponibilité configurable du faux client."""

        return self.ready

    def _raise_error(self) -> None:
        """Lève l'erreur configurée avant de retourner des données."""

        if self.error is not None:
            raise self.error

    async def list_products(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> ProductListData:
        """Enregistre l'appel de liste Produit."""

        self.calls.append(
            (
                "list_products",
                {
                    "limit": limit,
                    "offset": offset,
                },
            )
        )
        self._raise_error()
        return self.products

    async def get_product_details(
        self,
        product_id: int,
    ) -> ProductDetailsData:
        """Enregistre l'appel de détail Produit."""

        self.calls.append(
            (
                "get_product_details",
                {
                    "product_id": product_id,
                },
            )
        )
        self._raise_error()
        return self.details

    async def get_stock_by_product(
        self,
        product_id: int,
    ) -> StockByProductData:
        """Enregistre l'appel de stock Produit."""

        self.calls.append(
            (
                "get_stock_by_product",
                {
                    "product_id": product_id,
                },
            )
        )
        self._raise_error()
        return self.by_product

    async def get_stock_by_branch(
        self,
        branch_id: int,
    ) -> StockByBranchData:
        """Enregistre l'appel de stock Branche."""

        self.calls.append(
            (
                "get_stock_by_branch",
                {
                    "branch_id": branch_id,
                },
            )
        )
        self._raise_error()
        return self.by_branch

    async def check_shopping_list(
        self,
        items: list[ShoppingListItem],
    ) -> ShoppingListData:
        """Enregistre l'appel de liste d'achats."""

        self.calls.append(
            (
                "check_shopping_list",
                {
                    "items": [
                        item.model_dump()
                        for item in items
                    ],
                },
            )
        )
        self._raise_error()
        return self.shopping


@pytest.mark.parametrize(
    ("intent", "expected_call", "expected_type"),
    [
        (
            ProductListIntent(limit=10, offset=5),
            (
                "list_products",
                {
                    "limit": 10,
                    "offset": 5,
                },
            ),
            "product_list",
        ),
        (
            ProductDetailsIntent(product_id=12),
            (
                "get_product_details",
                {
                    "product_id": 12,
                },
            ),
            "product_details",
        ),
        (
            StockByProductIntent(product_id=12),
            (
                "get_stock_by_product",
                {
                    "product_id": 12,
                },
            ),
            "stock_by_product",
        ),
        (
            StockByBranchIntent(branch_id=3),
            (
                "get_stock_by_branch",
                {
                    "branch_id": 3,
                },
            ),
            "stock_by_branch",
        ),
        (
            ShoppingListIntent(
                items=[
                    {
                        "product_id": 12,
                        "quantity": 2,
                    }
                ]
            ),
            (
                "check_shopping_list",
                {
                    "items": [
                        {
                            "product_id": 12,
                            "quantity": 2,
                        }
                    ],
                },
            ),
            "shopping_list",
        ),
    ],
)
async def test_orchestrator_calls_exactly_one_expected_method(
    intent: QueryIntent,
    expected_call: tuple[str, object],
    expected_type: str,
) -> None:
    """Associe chaque intention à une seule méthode MCP."""

    router = FakeIntentRouter(intent)
    client = FakeMCPDataClient()
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle("question explicite")

    assert response.success is True
    assert response.type == expected_type
    assert client.calls == [expected_call]
    assert router.questions == ["question explicite"]


async def test_answer_builder_uses_only_validated_product_data() -> None:
    """Construit le texte de détail depuis les seuls champs MCP."""

    router = FakeIntentRouter(
        ProductDetailsIntent(product_id=12)
    )
    client = FakeMCPDataClient()
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle("détails du produit 12")

    assert response.answer == (
        "Le produit 12 est « Produit de test » et coûte 19,99 EUR."
    )
    assert response.data is client.details


@pytest.mark.parametrize(
    ("intent", "data_attribute", "empty_value", "expected_answer"),
    [
        (
            ProductListIntent(),
            "products",
            ProductListData(
                count=0,
                limit=20,
                offset=0,
                products=[],
            ),
            "Aucun produit n’a été trouvé.",
        ),
        (
            StockByProductIntent(product_id=12),
            "by_product",
            StockByProductData(
                product_id=12,
                branches=[],
            ),
            (
                "Le produit 12 n’est disponible dans aucune "
                "branche."
            ),
        ),
        (
            StockByBranchIntent(branch_id=3),
            "by_branch",
            StockByBranchData(
                branch=BranchData(
                    id=3,
                    name="Carcassonne",
                ),
                stocks=[],
            ),
            (
                "La branche 3 ne possède actuellement aucun "
                "produit en stock."
            ),
        ),
        (
            ShoppingListIntent(
                items=[
                    {
                        "product_id": 12,
                        "quantity": 2,
                    }
                ]
            ),
            "shopping",
            ShoppingListData(matching_branches=[]),
            (
                "Aucune branche ne peut satisfaire entièrement "
                "cette liste d’achats."
            ),
        ),
    ],
)
async def test_orchestrator_builds_honest_empty_responses(
    intent: QueryIntent,
    data_attribute: str,
    empty_value: object,
    expected_answer: str,
) -> None:
    """Ne transforme pas une liste vide en disponibilité fictive."""

    router = FakeIntentRouter(intent)
    client = FakeMCPDataClient()
    setattr(client, data_attribute, empty_value)
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle("question")

    assert response.answer == expected_answer
    assert len(client.calls) == 1


async def test_unsupported_intent_never_calls_mcp() -> None:
    """Retourne une clarification réussie sans fait métier."""

    router = FakeIntentRouter(
        UnsupportedIntent(reason="Demande ambiguë.")
    )
    client = FakeMCPDataClient()
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle("question ambiguë")

    assert response.type == "text"
    assert response.success is True
    assert response.data is None
    assert response.error is None
    assert "une seule action" in response.answer
    assert client.calls == []


async def test_disconnected_client_returns_error_before_routing() -> None:
    """Retourne une indisponibilité sans appel ni valeur inventée."""

    router = FakeIntentRouter(
        ProductDetailsIntent(product_id=12)
    )
    client = FakeMCPDataClient()
    client.ready = False
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle("question")

    assert isinstance(response, ErrorResponse)
    assert response.error.code == "service_unavailable"
    assert response.data is None
    assert router.questions == []
    assert client.calls == []


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            MCPConnectionError("contenu technique"),
            "service_unavailable",
        ),
        (
            MCPTimeoutError("contenu technique"),
            "service_timeout",
        ),
        (
            MCPProtocolError("contenu technique"),
            "invalid_service_response",
        ),
        (
            MCPInvalidArgumentError("contenu technique"),
            "invalid_parameters",
        ),
        (
            MCPClientError("contenu technique"),
            "client_error",
        ),
        (
            MCPToolResponseError(
                "get_product_details",
                "resource_not_found",
            ),
            "resource_not_found",
        ),
        (
            MCPToolResponseError(
                "get_product_details",
                "product_not_found",
            ),
            "resource_not_found",
        ),
        (
            MCPToolResponseError(
                "get_stock_by_branch",
                "branch_not_found",
            ),
            "resource_not_found",
        ),
        (
            MCPToolResponseError(
                "get_product_details",
                "service_timeout",
            ),
            "service_timeout",
        ),
        (
            MCPToolResponseError(
                "get_product_details",
                "unknown_error",
            ),
            "client_error",
        ),
    ],
)
async def test_orchestrator_maps_expected_mcp_errors(
    error: Exception,
    expected_code: str,
) -> None:
    """Mappe les erreurs sans exposer leur contenu technique."""

    router = FakeIntentRouter(
        ProductDetailsIntent(product_id=12)
    )
    client = FakeMCPDataClient()
    client.error = error
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle("question")

    assert isinstance(response, ErrorResponse)
    assert response.error.code == expected_code
    assert response.data is None
    assert "contenu technique" not in response.answer
    assert "contenu technique" not in response.error.message
    assert len(client.calls) == 1


async def test_unexpected_python_bug_is_not_masked() -> None:
    """Laisse remonter une exception étrangère aux erreurs MCP."""

    router = FakeIntentRouter(
        ProductDetailsIntent(product_id=12)
    )
    client = FakeMCPDataClient()
    client.error = RuntimeError("bug inattendu")
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    with pytest.raises(RuntimeError, match="bug inattendu"):
        await orchestrator.handle("question")

    assert len(client.calls) == 1
