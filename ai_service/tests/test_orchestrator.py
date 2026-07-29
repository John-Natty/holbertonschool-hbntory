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


def product_data(
    *,
    product_id: int = 12,
    name: str = "Produit de test",
    unit_price: float = 19.99,
    currency: str = "EUR",
) -> ProductData:
    """Construit un produit validé commun aux tests."""

    return ProductData(
        id=product_id,
        sku="HB-TEST-0012",
        name=name,
        description="Description.",
        category="Tests",
        brand="HBntory",
        supplier_id="SUP-001",
        supplier_name="Fournisseur",
        unit_price=unit_price,
        currency=currency,
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
                    "product_name": "Produit de test",
                    "unit_price": 49.99,
                    "currency": "EUR",
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

    async def ensure_connected(self) -> bool:
        """Retourne la disponibilité simulée sans appel métier."""

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
        branch_id: int | None = None,
        branch_name: str | None = None,
    ) -> StockByBranchData:
        """Enregistre l'appel de stock Branche."""

        self.calls.append(
            (
                "get_stock_by_branch",
                {
                    "branch_id": branch_id,
                    **(
                        {"branch_name": branch_name}
                        if branch_name is not None
                        else {}
                    ),
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


class FakeAnswerGenerator:
    """Simule une rédaction naturelle et mémorise ses appels."""

    def __init__(self) -> None:
        """Prépare la liste des appels."""

        self.calls: list[tuple[str, object]] = []

    async def generate(
        self,
        question: str,
        response: object,
    ) -> str:
        """Retourne une formulation de test."""

        self.calls.append((question, response))
        return "Réponse naturelle de test."


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


async def test_product_list_answer_displays_each_validated_product() -> None:
    """Affiche identifiants, noms et prix avec un unique appel MCP."""

    router = FakeIntentRouter(ProductListIntent(limit=10))
    client = FakeMCPDataClient()
    client.products = ProductListData(
        count=2,
        limit=10,
        offset=0,
        products=[
            product_data(
                product_id=4,
                name="Écran compact",
                unit_price=169.99,
                currency="USD",
            ),
            product_data(
                product_id=3,
                name="Écran laboratoire",
                unit_price=229.5,
                currency="USD",
            ),
        ],
    )
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle(
        "liste les 10 premiers produits"
    )

    assert response.answer == (
        "2 produits ont été trouvés :\n\n"
        "- #4 — Écran compact — 169,99 USD\n"
        "- #3 — Écran laboratoire — 229,50 USD"
    )
    assert response.data is client.products
    assert client.calls == [
        (
            "list_products",
            {
                "limit": 10,
                "offset": 0,
            },
        )
    ]


async def test_product_list_answer_displays_one_product() -> None:
    """Présente également les données lorsqu'un seul produit existe."""

    data = ProductListData(
        count=1,
        limit=1,
        offset=0,
        products=[
            product_data(
                product_id=8,
                name="Clavier",
                unit_price=49.9,
            )
        ],
    )

    response = AnswerBuilder().product_list(data)

    assert response.answer == (
        "1 produit a été trouvé :\n\n"
        "- #8 — Clavier — 49,90 EUR"
    )
    assert response.data is data


async def test_product_list_answer_respects_response_limit() -> None:
    """N'affiche jamais plus de lignes que la limite validée."""

    products = [
        product_data(
            product_id=index,
            name=f"Produit {index}",
        )
        for index in range(1, 11)
    ]
    data = ProductListData(
        count=10,
        limit=5,
        offset=0,
        products=products,
    )

    response = AnswerBuilder().product_list(data)

    assert response.answer.startswith(
        "Voici 5 produits affichés sur 10 au total :"
    )
    assert response.answer.count("\n- #") == 5
    assert "- #5 — Produit 5" in response.answer
    assert "- #6 — Produit 6" not in response.answer
    assert response.data.products == products


async def test_product_list_answer_distinguishes_page_from_total() -> None:
    """Distingue le nombre affiché du total annoncé par le catalogue."""

    data = ProductListData(
        count=39,
        limit=20,
        offset=0,
        products=[
            product_data(
                product_id=index,
                name=f"Produit {index}",
            )
            for index in range(1, 21)
        ],
    )

    response = AnswerBuilder().product_list(data)

    assert response.answer.startswith(
        "Voici 20 produits affichés sur 39 au total :"
    )


async def test_long_product_list_skips_slow_natural_generation() -> None:
    """Conserve la liste exhaustive déterministe au-delà de dix produits."""

    router = FakeIntentRouter(
        ProductListIntent(
            limit=20,
            offset=0,
        )
    )
    client = FakeMCPDataClient()
    client.products = ProductListData(
        count=39,
        limit=20,
        offset=0,
        products=[
            product_data(
                product_id=index,
                name=f"Produit {index}",
            )
            for index in range(1, 21)
        ],
    )
    generator = FakeAnswerGenerator()
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
        answer_generator=generator,
    )

    response = await orchestrator.handle(
        "liste les produits du catalogue"
    )

    assert response.answer.startswith(
        "Voici 20 produits affichés sur 39 au total :"
    )
    assert generator.calls == []


async def test_product_list_answer_displays_ten_products() -> None:
    """Présente les dix éléments d'une page complète."""

    products = [
        product_data(
            product_id=index,
            name=f"Produit {index}",
            unit_price=index + 0.5,
        )
        for index in range(1, 11)
    ]
    data = ProductListData(
        count=10,
        limit=10,
        offset=0,
        products=products,
    )

    response = AnswerBuilder().product_list(data)

    assert response.answer.startswith(
        "10 produits ont été trouvés :"
    )
    assert response.answer.count("\n- #") == 10
    assert "- #1 — Produit 1 — 1,50 EUR" in response.answer
    assert "- #10 — Produit 10 — 10,50 EUR" in response.answer
    assert response.data is data


async def test_orchestrator_rejects_incoherent_product_page() -> None:
    """Refuse qu'une réponse MCP dépasse la pagination demandée."""

    router = FakeIntentRouter(ProductListIntent(limit=5))
    client = FakeMCPDataClient()
    client.products = ProductListData(
        count=10,
        limit=10,
        offset=0,
        products=[product_data()],
    )
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle(
        "liste les cinq premiers produits"
    )

    assert isinstance(response, ErrorResponse)
    assert response.error.code == "invalid_service_response"
    assert client.calls == [
        (
            "list_products",
            {
                "limit": 5,
                "offset": 0,
            },
        )
    ]


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
                "La branche Carcassonne ne possède actuellement aucun "
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


async def test_stock_by_branch_lists_each_validated_stock() -> None:
    """Liste les identifiants et quantités sans appel supplémentaire."""

    router = FakeIntentRouter(StockByBranchIntent(branch_id=3))
    client = FakeMCPDataClient()
    client.by_branch = StockByBranchData(
        branch=BranchData(
            id=3,
            name="Carcassonne",
        ),
        stocks=[
            {
                "product_id": 4,
                "product_name": "Clavier compact",
                "unit_price": 49.99,
                "currency": "EUR",
                "quantity": 1,
            },
            {
                "product_id": 7,
                "product_name": "Écran 24 pouces",
                "unit_price": 169.99,
                "currency": "EUR",
                "quantity": 5,
            },
        ],
    )
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle("stock de la branche 3")

    assert response.answer == (
        "La branche Carcassonne possède 2 références en stock :\n"
        "- Produit n°4 — Quantité : 1 — Nom : Clavier compact — "
        "Prix unitaire : 49,99 EUR\n"
        "- Produit n°7 — Quantité : 5 — Nom : Écran 24 pouces — "
        "Prix unitaire : 169,99 EUR"
    )
    assert response.data is client.by_branch
    assert client.calls == [
        (
            "get_stock_by_branch",
            {
                "branch_id": 3,
            },
        )
    ]


async def test_stock_by_branch_name_makes_one_mcp_call() -> None:
    """Transmet uniquement le nom puis utilise la branche réelle retournée."""

    router = FakeIntentRouter(
        StockByBranchIntent(branch_name="toulouse")
    )
    client = FakeMCPDataClient()
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle("stock de Toulouse")

    assert response.type == "stock_by_branch"
    assert client.calls == [
        (
            "get_stock_by_branch",
            {
                "branch_id": None,
                "branch_name": "toulouse",
            },
        )
    ]


async def test_shopping_list_names_each_matching_branch() -> None:
    """Nomme toutes les branches validées sans inventer de résultat."""

    router = FakeIntentRouter(
        ShoppingListIntent(
            items=[
                {
                    "product_id": 12,
                    "quantity": 2,
                }
            ]
        )
    )
    client = FakeMCPDataClient()
    client.shopping = ShoppingListData(
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
            },
            {
                "branch_id": 2,
                "branch_name": "Carcassonne",
                "items": [
                    {
                        "product_id": 12,
                        "requested_quantity": 2,
                        "available_quantity": 3,
                    }
                ],
            },
        ]
    )
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle(
        "où acheter le produit 12 x2"
    )

    assert response.answer == (
        "Les branches Toulouse et Carcassonne peuvent satisfaire "
        "entièrement cette liste d’achats."
    )
    assert response.data is client.shopping
    assert "Albi" not in response.answer
    assert client.calls == [
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
        )
    ]


async def test_unsupported_intent_never_calls_mcp() -> None:
    """Retourne le refus hors domaine sans fait métier."""

    router = FakeIntentRouter(
        UnsupportedIntent(
            reason="Demande hors domaine.",
            reason_code="out_of_domain",
        )
    )
    client = FakeMCPDataClient()
    orchestrator = QueryOrchestrator(
        router,
        client,
        AnswerBuilder(),
    )

    response = await orchestrator.handle("question ambiguë")

    assert response.type == "unsupported"
    assert response.success is True
    assert response.data is None
    assert response.error is None
    assert response.answer == (
        "Je peux uniquement répondre aux questions concernant les produits, "
        "les stocks, les branches et les listes d’achats de HBntory."
    )
    assert client.calls == []


async def test_disconnected_client_returns_error_after_routing() -> None:
    """Classe d'abord, puis retourne l'indisponibilité sans fait inventé."""

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
    assert router.questions == ["question"]
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
