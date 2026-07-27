"""Tests du routeur d'intention déterministe."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.models.intents import (
    ProductDetailsIntent,
    ProductListIntent,
    QueryIntent,
    ShoppingListIntent,
    StockByBranchIntent,
    StockByProductIntent,
    UnsupportedIntent,
)
from app.services.intent_router import RuleBasedIntentRouter


INTENT_ADAPTER = TypeAdapter(QueryIntent)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "liste les produits",
            {
                "type": "product_list",
                "limit": 20,
                "offset": 0,
            },
        ),
        (
            "affiche les produits",
            {
                "type": "product_list",
                "limit": 20,
                "offset": 0,
            },
        ),
        (
            "quels sont les produits ?",
            {
                "type": "product_list",
                "limit": 20,
                "offset": 0,
            },
        ),
        (
            "Montre-moi les produits",
            {
                "type": "product_list",
                "limit": 20,
                "offset": 0,
            },
        ),
        (
            "liste les 10 premiers produits",
            {
                "type": "product_list",
                "limit": 10,
                "offset": 0,
            },
        ),
        (
            "affiche les produits à partir de 20",
            {
                "type": "product_list",
                "limit": 20,
                "offset": 20,
            },
        ),
        (
            "liste des produits",
            {
                "type": "product_list",
                "limit": 20,
                "offset": 0,
            },
        ),
        (
            "affiche des produits",
            {
                "type": "product_list",
                "limit": 20,
                "offset": 0,
            },
        ),
        (
            "liste des produits à partir de 20",
            {
                "type": "product_list",
                "limit": 20,
                "offset": 20,
            },
        ),
        (
            "détails du produit 12",
            {
                "type": "product_details",
                "product_id": 12,
            },
        ),
        (
            "montre le produit 12",
            {
                "type": "product_details",
                "product_id": 12,
            },
        ),
        (
            "informations sur le produit 12",
            {
                "type": "product_details",
                "product_id": 12,
            },
        ),
        (
            "quel est le prix du produit 12",
            {
                "type": "product_details",
                "product_id": 12,
            },
        ),
        (
            "où trouver le produit 12",
            {
                "type": "stock_by_product",
                "product_id": 12,
            },
        ),
        (
            "dans quelles branches est disponible le produit 12",
            {
                "type": "stock_by_product",
                "product_id": 12,
            },
        ),
        (
            "stock du produit 12",
            {
                "type": "stock_by_product",
                "product_id": 12,
            },
        ),
        (
            "combien reste-t-il du produit 12 ?",
            {
                "type": "stock_by_product",
                "product_id": 12,
            },
        ),
        (
            "stock de la branche 3",
            {
                "type": "stock_by_branch",
                "branch_id": 3,
            },
        ),
        (
            "produits de la branche 3",
            {
                "type": "stock_by_branch",
                "branch_id": 3,
            },
        ),
        (
            "que contient la branche 3",
            {
                "type": "stock_by_branch",
                "branch_id": 3,
            },
        ),
        (
            "liste le stock de la branche 3",
            {
                "type": "stock_by_branch",
                "branch_id": 3,
            },
        ),
        (
            "liste d'achats : produit 12 x2, produit 7 x1",
            {
                "type": "shopping_list",
                "items": [
                    {
                        "product_id": 12,
                        "quantity": 2,
                    },
                    {
                        "product_id": 7,
                        "quantity": 1,
                    },
                ],
            },
        ),
        (
            "vérifie la liste : 12 x2, 7 x1",
            {
                "type": "shopping_list",
                "items": [
                    {
                        "product_id": 12,
                        "quantity": 2,
                    },
                    {
                        "product_id": 7,
                        "quantity": 1,
                    },
                ],
            },
        ),
        (
            "où acheter 12 x2 et 7 x1",
            {
                "type": "shopping_list",
                "items": [
                    {
                        "product_id": 12,
                        "quantity": 2,
                    },
                    {
                        "product_id": 7,
                        "quantity": 1,
                    },
                ],
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_router_recognizes_documented_questions(
    question: str,
    expected: dict[str, object],
) -> None:
    """Reconnaît chaque formulation explicitement documentée."""

    router = RuleBasedIntentRouter()

    intent = await router.resolve(question)

    assert intent.model_dump() == expected


@pytest.mark.asyncio
async def test_router_normalizes_spaces_case_and_accents() -> None:
    """Ignore les variations superficielles sans élargir le contrat."""

    router = RuleBasedIntentRouter()

    intent = await router.resolve(
        "  OÙ   TROUVER le PRODUIT 12 ?  "
    )

    assert intent == StockByProductIntent(product_id=12)


@pytest.mark.asyncio
async def test_router_preserves_shopping_list_duplicates() -> None:
    """Ne normalise pas silencieusement les doublons de la demande."""

    router = RuleBasedIntentRouter()

    intent = await router.resolve(
        "liste d'achats : produit 12 x1, produit 12 x2"
    )

    assert isinstance(intent, ShoppingListIntent)
    assert [
        item.model_dump()
        for item in intent.items
    ] == [
        {
            "product_id": 12,
            "quantity": 1,
        },
        {
            "product_id": 12,
            "quantity": 2,
        },
    ]


@pytest.mark.parametrize(
    "question",
    [
        "montre-moi ce produit",
        "où est-il disponible",
        "stock de la branche",
        "je cherche un produit",
        "produit 12 ou produit 13",
        (
            "montre les détails du produit 12 et le stock "
            "de la branche 3"
        ),
        "détails du produit 0",
        "détails du produit -1",
        "stock du produit vrai",
        "stock de la branche false",
        "liste les 0 premiers produits",
        "liste les -1 premiers produits",
        "affiche les produits à partir de -1",
        "liste d'achats :",
        "liste d'achats : produit 12",
        "liste d'achats : produit 12 x0",
        "liste d'achats : produit 12 x-1",
        "liste d'achats : savon x2",
        "question totalement inconnue",
        "   ",
    ],
)
@pytest.mark.asyncio
async def test_router_refuses_ambiguous_or_invalid_questions(
    question: str,
) -> None:
    """Demande une précision au lieu d'inventer une valeur."""

    router = RuleBasedIntentRouter()

    intent = await router.resolve(question)

    assert isinstance(intent, UnsupportedIntent)
    assert intent.reason


def test_intent_union_is_strict() -> None:
    """Refuse les booléens, listes vides et champs supplémentaires."""

    invalid_payloads = [
        {
            "type": "product_details",
            "product_id": True,
        },
        {
            "type": "product_list",
            "limit": 20,
            "offset": 0,
            "extra": True,
        },
        {
            "type": "shopping_list",
            "items": [],
        },
    ]

    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            INTENT_ADAPTER.validate_python(payload)


def test_each_intent_model_uses_expected_discriminator() -> None:
    """Confirme les six variantes de l'union interne."""

    intents = [
        ProductListIntent(),
        ProductDetailsIntent(product_id=12),
        StockByProductIntent(product_id=12),
        StockByBranchIntent(branch_id=3),
        ShoppingListIntent(
            items=[
                {
                    "product_id": 12,
                    "quantity": 2,
                }
            ]
        ),
        UnsupportedIntent(reason="Demande inconnue."),
    ]

    assert {
        intent.type
        for intent in intents
    } == {
        "product_list",
        "product_details",
        "stock_by_product",
        "stock_by_branch",
        "shopping_list",
        "unsupported",
    }
