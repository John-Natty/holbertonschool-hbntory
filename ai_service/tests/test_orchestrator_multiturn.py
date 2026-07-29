"""Scénarios multi-tour de bout en bout autour de QueryOrchestrator."""

from __future__ import annotations

import asyncio

import pytest

from app.models.data import (
    BranchData,
    ProductData,
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
)
from app.models.mcp import ShoppingListItem
from app.models.query import QueryRequest
from app.services.answer_builder import AnswerBuilder
from app.services.context_resolver import ContextResolver
from app.services.intent_classifier import IntentClassifier
from app.services.orchestrator import QueryOrchestrator


pytestmark = pytest.mark.asyncio


def _product(product_id: int) -> ProductData:
    """Construit une fiche Produit strictement valide."""

    return ProductData(
        id=product_id,
        sku=f"HB-{product_id:04d}",
        name=f"Produit {product_id}",
        description="Produit de test conversationnel.",
        category="Tests",
        brand="HBntory",
        supplier_id="SUP-001",
        supplier_name="Fournisseur",
        unit_price=float(product_id),
        currency="EUR",
        discontinued=False,
        weight_kg=1.0,
        tags=["test"],
        updated_at="2026-07-28T10:00:00Z",
        supplier=None,
    )


class RecordingMCPClient:
    """Faux MCP en lecture seule qui trace exactement chaque outil métier."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.details_entered = asyncio.Event()
        self.release_details = asyncio.Event()
        self.block_product_details = False

    @property
    def is_ready(self) -> bool:
        return True

    async def ensure_connected(self) -> bool:
        return True

    async def list_products(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> ProductListData:
        self.calls.append(
            ("list_products", {"limit": limit, "offset": offset})
        )
        identifiers = [4, 3, 13, 37, 29][:limit]
        return ProductListData(
            count=5,
            limit=limit,
            offset=offset,
            products=[_product(identifier) for identifier in identifiers],
        )

    async def get_product_details(
        self,
        product_id: int,
    ) -> ProductDetailsData:
        self.calls.append(
            ("get_product_details", {"product_id": product_id})
        )
        if self.block_product_details:
            self.details_entered.set()
            await self.release_details.wait()
        return ProductDetailsData(product=_product(product_id))

    async def get_stock_by_product(
        self,
        product_id: int,
    ) -> StockByProductData:
        self.calls.append(
            ("get_stock_by_product", {"product_id": product_id})
        )
        branches = {
            11: [
                {
                    "branch_id": 2,
                    "branch_name": "Carcassonne",
                    "quantity": 10,
                }
            ],
            10: [
                {
                    "branch_id": 1,
                    "branch_name": "Toulouse",
                    "quantity": 4,
                }
            ],
            3: [
                {
                    "branch_id": 1,
                    "branch_name": "Toulouse",
                    "quantity": 2,
                }
            ],
        }.get(product_id, [])
        return StockByProductData(
            product_id=product_id,
            branches=branches,
        )

    async def get_stock_by_branch(
        self,
        branch_id: int | None = None,
        branch_name: str | None = None,
    ) -> StockByBranchData:
        self.calls.append(
            (
                "get_stock_by_branch",
                {
                    "branch_id": branch_id,
                    "branch_name": branch_name,
                },
            )
        )
        requested = branch_name or (
            "Toulouse" if branch_id == 1 else "Carcassonne"
        )
        is_toulouse = requested.casefold() == "toulouse"
        return StockByBranchData(
            branch=BranchData(
                id=1 if is_toulouse else 2,
                name="Toulouse" if is_toulouse else "Carcassonne",
            ),
            stocks=[
                {
                    "product_id": 4 if is_toulouse else 11,
                    "product_name": (
                        "Produit 4" if is_toulouse else "Produit 11"
                    ),
                    "unit_price": 4.0 if is_toulouse else 11.0,
                    "currency": "EUR",
                    "quantity": 5 if is_toulouse else 10,
                }
            ],
        )

    async def check_shopping_list(
        self,
        items: list[ShoppingListItem],
    ) -> ShoppingListData:
        serialized = [item.model_dump() for item in items]
        self.calls.append(("check_shopping_list", serialized))
        return ShoppingListData(
            matching_branches=[
                {
                    "branch_id": 1,
                    "branch_name": "Toulouse",
                    "items": [
                        {
                            "product_id": item.product_id,
                            "requested_quantity": item.quantity,
                            "available_quantity": item.quantity + 5,
                        }
                        for item in items
                    ],
                }
            ]
        )


@pytest.fixture
def system() -> tuple[QueryOrchestrator, RecordingMCPClient]:
    """Assemble la vraie mémoire et le vrai fallback conversationnel."""

    client = RecordingMCPClient()
    classifier = IntentClassifier(
        context_resolver=ContextResolver(),
    )
    orchestrator = QueryOrchestrator(
        classifier,
        client,
        AnswerBuilder(),
    )
    return orchestrator, client


async def _ask(
    orchestrator: QueryOrchestrator,
    question: str,
    conversation_id: str | None = None,
):
    """Envoie le contrat public complet à l'orchestrateur."""

    return await orchestrator.handle(
        QueryRequest(
            conversation_id=conversation_id,
            question=question,
        )
    )


async def test_product_then_branch_followup_uses_one_stock_call_per_turn(
    system: tuple[QueryOrchestrator, RecordingMCPClient],
) -> None:
    """Conserve le produit 11 et ajoute Toulouse au second tour."""

    orchestrator, client = system
    first = await _ask(
        orchestrator,
        "Où est disponible le produit 11 ?",
    )
    assert client.calls == [
        ("get_stock_by_product", {"product_id": 11})
    ]

    second = await _ask(
        orchestrator,
        "Et à Toulouse ?",
        first.conversation_id,
    )

    assert second.conversation_id == first.conversation_id
    assert second.type == "stock_by_product"
    assert "n’est pas disponible" in second.answer
    assert "Toulouse" in second.answer
    assert "Carcassonne" in second.answer
    assert client.calls == [
        ("get_stock_by_product", {"product_id": 11}),
        ("get_stock_by_product", {"product_id": 11}),
    ]


async def test_product_list_then_second_uses_real_second_identifier(
    system: tuple[QueryOrchestrator, RecordingMCPClient],
) -> None:
    """Résout « deuxième » avec l'ordre [4, 3, 13, 37, 29]."""

    orchestrator, client = system
    first = await _ask(
        orchestrator,
        "Montre-moi les cinq premiers produits.",
    )
    assert client.calls == [
        ("list_products", {"limit": 5, "offset": 0})
    ]

    second = await _ask(
        orchestrator,
        "Donne-moi plus d’informations sur le deuxième.",
        first.conversation_id,
    )

    assert second.conversation_id == first.conversation_id
    assert second.type == "product_details"
    assert second.data.product.id == 3
    assert client.calls[-1] == (
        "get_product_details",
        {"product_id": 3},
    )
    assert len(client.calls) == 2


async def test_branch_then_other_branch_preserves_stock_operation(
    system: tuple[QueryOrchestrator, RecordingMCPClient],
) -> None:
    """Remplace Toulouse par Carcassonne sans changer d'outil métier."""

    orchestrator, client = system
    first = await _ask(
        orchestrator,
        "Qu’est-ce qu’il reste à Toulouse ?",
    )
    second = await _ask(
        orchestrator,
        "Et à Carcassonne ?",
        first.conversation_id,
    )

    assert second.conversation_id == first.conversation_id
    assert second.type == "stock_by_branch"
    assert second.data.branch.name == "Carcassonne"
    assert client.calls == [
        (
            "get_stock_by_branch",
            {"branch_id": None, "branch_name": "Toulouse"},
        ),
        (
            "get_stock_by_branch",
            {"branch_id": None, "branch_name": "Carcassonne"},
        ),
    ]


async def test_product_then_pronoun_switches_to_stock_once(
    system: tuple[QueryOrchestrator, RecordingMCPClient],
) -> None:
    """Réutilise le produit 10 pour « Où puis-je le trouver ? »."""

    orchestrator, client = system
    first = await _ask(orchestrator, "Parle-moi du produit 10.")
    second = await _ask(
        orchestrator,
        "Où puis-je le trouver ?",
        first.conversation_id,
    )

    assert second.conversation_id == first.conversation_id
    assert second.type == "stock_by_product"
    assert second.data.product_id == 10
    assert client.calls == [
        ("get_product_details", {"product_id": 10}),
        ("get_stock_by_product", {"product_id": 10}),
    ]


async def test_shopping_followup_updates_only_product_eight_quantity(
    system: tuple[QueryOrchestrator, RecordingMCPClient],
) -> None:
    """Conserve 4×2 puis remplace 8×1 par 8×3 avant l'appel."""

    orchestrator, client = system
    first = await _ask(
        orchestrator,
        "Je cherche deux produits 4 et un produit 8.",
    )
    second = await _ask(
        orchestrator,
        "Et si j’en veux trois du produit 8 ?",
        first.conversation_id,
    )

    assert second.conversation_id == first.conversation_id
    assert second.type == "shopping_list"
    assert client.calls == [
        (
            "check_shopping_list",
            [
                {"product_id": 4, "quantity": 2},
                {"product_id": 8, "quantity": 1},
            ],
        ),
        (
            "check_shopping_list",
            [
                {"product_id": 4, "quantity": 2},
                {"product_id": 8, "quantity": 3},
            ],
        ),
    ]


async def test_out_of_domain_followup_makes_zero_business_call(
    system: tuple[QueryOrchestrator, RecordingMCPClient],
) -> None:
    """La mémoire produit ne contourne jamais le refus HBntory."""

    orchestrator, client = system
    first = await _ask(
        orchestrator,
        "Où est disponible le produit 11 ?",
    )
    calls_before = list(client.calls)

    second = await _ask(
        orchestrator,
        "Et quelle est la météo ?",
        first.conversation_id,
    )

    assert second.conversation_id == first.conversation_id
    assert second.type == "unsupported"
    assert client.calls == calls_before


async def test_two_conversations_remain_isolated_when_followups_overlap(
    system: tuple[QueryOrchestrator, RecordingMCPClient],
) -> None:
    """Deux sessions concurrentes ne mélangent jamais leurs produits."""

    orchestrator, client = system
    product_ten = await _ask(
        orchestrator,
        "Parle-moi du produit 10.",
    )
    product_eleven = await _ask(
        orchestrator,
        "Parle-moi du produit 11.",
    )
    calls_before = len(client.calls)

    ten_stock, eleven_stock = await asyncio.gather(
        _ask(
            orchestrator,
            "Où puis-je le trouver ?",
            product_ten.conversation_id,
        ),
        _ask(
            orchestrator,
            "Où puis-je le trouver ?",
            product_eleven.conversation_id,
        ),
    )

    assert product_ten.conversation_id != product_eleven.conversation_id
    assert ten_stock.data.product_id == 10
    assert eleven_stock.data.product_id == 11
    assert len(client.calls) == calls_before + 2
    assert {
        call[1]["product_id"]
        for call in client.calls[calls_before:]
    } == {10, 11}


async def test_same_conversation_serializes_dependent_followups(
    system: tuple[QueryOrchestrator, RecordingMCPClient],
) -> None:
    """Le second suivi attend que le premier ait mémorisé le produit 3."""

    orchestrator, client = system
    first = await _ask(
        orchestrator,
        "Montre-moi les cinq premiers produits.",
    )
    client.block_product_details = True

    details_task = asyncio.create_task(
        _ask(
            orchestrator,
            "Donne-moi plus d’informations sur le deuxième.",
            first.conversation_id,
        )
    )
    await asyncio.wait_for(client.details_entered.wait(), timeout=0.5)
    calls_after_details_entered = len(client.calls)
    stock_task = asyncio.create_task(
        _ask(
            orchestrator,
            "Où puis-je le trouver ?",
            first.conversation_id,
        )
    )

    await asyncio.sleep(0.02)
    assert len(client.calls) == calls_after_details_entered

    client.release_details.set()
    details, stock = await asyncio.gather(details_task, stock_task)

    assert details.data.product.id == 3
    assert stock.data.product_id == 3
    assert client.calls[-2:] == [
        ("get_product_details", {"product_id": 3}),
        ("get_stock_by_product", {"product_id": 3}),
    ]
