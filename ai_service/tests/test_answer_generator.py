"""Tests du générateur naturel et de ses claims relationnels."""

from __future__ import annotations

import json

import pytest

from app.errors import GeneratedAnswerError, NVIDIAConnectionError
from app.models.data import (
    BranchData,
    MatchingBranchData,
    MatchingItemData,
    ProductBranchData,
    ProductData,
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
    StockData,
)
from app.models.conversation import validate_conversation_id
from app.models.generation import (
    FactClaim,
    ProductAvailabilityClaim,
    ProductPriceClaim,
)
from app.models.intents import (
    ProductDetailsIntent,
    StockByProductIntent,
)
from app.models.query import QueryRequest
from app.services.answer_builder import AnswerBuilder
from app.services.answer_generator import (
    AnswerGenerator,
    build_expected_claims,
)
from app.services.orchestrator import QueryOrchestrator


pytestmark = pytest.mark.asyncio
CONVERSATION_ID = "A" * 32


def product_data(
    product_id: int = 4,
    *,
    name: str = "Écran compact",
    price: float = 169.99,
) -> ProductData:
    """Construit un produit complet déjà validé."""

    return ProductData(
        id=product_id,
        sku=f"HB-{product_id:04d}",
        name=name,
        description="Description publique",
        category="Écrans",
        brand="LabForge",
        supplier_id="SUP-004",
        supplier_name="Fournisseur",
        unit_price=price,
        currency="EUR",
        discontinued=False,
        weight_kg=3.5,
        tags=["écran"],
        updated_at="2026-07-28T12:00:00Z",
        supplier=None,
    )


class FakeCompletionClient:
    """Retourne un JSON contrôlé et conserve les messages reçus."""

    def __init__(
        self,
        content: str = "",
        error: Exception | None = None,
    ) -> None:
        self.content = content
        self.error = error
        self.calls: list[tuple[list[dict[str, str]], int]] = []

    async def complete(
        self,
        messages,
        *,
        max_tokens: int,
    ) -> str:
        """Simule exactement une complétion fournisseur."""

        self.calls.append((list(messages), max_tokens))
        if self.error is not None:
            raise self.error
        return self.content


def product_details_response():
    """Retourne une réponse déterministe avec identifiant de conversation."""

    return AnswerBuilder().product_details(
        ProductDetailsData(product=product_data()),
        conversation_id=CONVERSATION_ID,
    )


def product_list_response():
    """Retourne deux relations prix faciles à permuter."""

    return AnswerBuilder().product_list(
        ProductListData(
            count=2,
            limit=20,
            offset=0,
            products=[
                product_data(
                    1,
                    name="Clavier compact",
                    price=49.99,
                ),
                product_data(
                    2,
                    name="Écran étudiant",
                    price=169.99,
                ),
            ],
        ),
        conversation_id=CONVERSATION_ID,
    )


def stock_response():
    """Retourne deux stocks dont les relations sont distinctes."""

    return AnswerBuilder().stock_by_product(
        StockByProductData(
            product_id=7,
            branches=[
                ProductBranchData(
                    branch_id=1,
                    branch_name="Toulouse",
                    quantity=3,
                ),
                ProductBranchData(
                    branch_id=2,
                    branch_name="Carcassonne",
                    quantity=9,
                ),
            ],
        ),
        conversation_id=CONVERSATION_ID,
    )


def branch_stock_response():
    """Retourne une ligne complète de stock par branche."""

    return AnswerBuilder().stock_by_branch(
        StockByBranchData(
            branch=BranchData(id=1, name="Toulouse"),
            stocks=[
                StockData(
                    product_id=4,
                    product_name="Écran compact",
                    unit_price=169.99,
                    currency="EUR",
                    quantity=12,
                )
            ],
        ),
        conversation_id=CONVERSATION_ID,
    )


def shopping_response():
    """Retourne une branche satisfaisant deux quantités demandées."""

    return AnswerBuilder().shopping_list(
        ShoppingListData(
            matching_branches=[
                MatchingBranchData(
                    branch_id=2,
                    branch_name="Carcassonne",
                    items=[
                        MatchingItemData(
                            product_id=4,
                            requested_quantity=2,
                            available_quantity=7,
                        ),
                        MatchingItemData(
                            product_id=8,
                            requested_quantity=3,
                            available_quantity=3,
                        ),
                    ],
                )
            ]
        ),
        conversation_id=CONVERSATION_ID,
    )


def generated_json(
    claims: list[FactClaim],
    *,
    text_overrides: dict[int, str] | None = None,
) -> str:
    """Sérialise un segment factuel contrôlé pour chaque claim."""

    overrides = text_overrides or {}
    return json.dumps(
        {
            "segments": [
                {
                    "type": "fact",
                    "text": overrides.get(
                        index,
                        fact_text(claim),
                    ),
                    "claim": claim.model_dump(mode="json"),
                }
                for index, claim in enumerate(claims)
            ]
        },
        ensure_ascii=False,
    )


def fact_text(claim: FactClaim) -> str:
    """Construit une phrase complète adaptée à chaque claim testé."""

    if claim.type == "product_price":
        return (
            f"Le produit {claim.product_id}, {claim.product_name}, "
            f"coûte {claim.unit_price:.2f} {claim.currency}."
        )
    if claim.type == "product_list_summary":
        return (
            f"{claim.displayed_count} produits sont affichés sur "
            f"{claim.total_count} produits."
        )
    if claim.type == "product_stock_summary":
        return (
            f"Le produit {claim.product_id} est disponible dans "
            f"{claim.available_branch_count} branches."
        )
    if claim.type == "product_availability":
        branch = claim.branch_name or f"n°{claim.branch_id}"
        if claim.available:
            return (
                f"Le produit {claim.product_id} est disponible dans "
                f"la branche {branch} avec {claim.quantity} unités."
            )
        return (
            f"Le produit {claim.product_id} n'est pas disponible "
            f"dans la branche {branch}."
        )
    if claim.type == "branch_stock_summary":
        return (
            f"La branche {claim.branch_name} possède "
            f"{claim.stock_count} référence en stock."
        )
    if claim.type == "branch_stock_item":
        return (
            f"Dans la branche {claim.branch_name}, le produit "
            f"{claim.product_id}, {claim.product_name}, possède une "
            f"quantité de {claim.quantity} et coûte "
            f"{claim.unit_price:.2f} {claim.currency}."
        )
    if claim.type == "shopping_summary":
        return (
            f"{claim.matching_branch_count} branche peut satisfaire "
            "entièrement la liste."
        )
    if claim.type == "shopping_branch":
        return (
            f"La branche {claim.branch_name} peut satisfaire "
            "entièrement la liste."
        )
    raise AssertionError(f"Claim non pris en charge : {claim.type}")


async def test_accepts_valid_structured_answer() -> None:
    """Accepte un texte naturel lorsque son unique relation est exacte."""

    response = product_details_response()
    claims = build_expected_claims(response)
    content = json.loads(generated_json(claims))
    content["segments"].insert(
        0,
        {
            "type": "natural",
            "text": "Bien sûr, voici ce que j'ai trouvé :",
        },
    )
    client = FakeCompletionClient(
        json.dumps(content, ensure_ascii=False)
    )

    result = await AnswerGenerator(client, 800).generate(
        "Donne-moi les détails du produit 4.",
        response,
        ProductDetailsIntent(product_id=4),
    )

    assert "Écran compact" in result
    assert "169.99 EUR" in result
    assert len(client.calls) == 1
    assert client.calls[0][1] == 800


async def test_accepts_neutral_natural_product_transition() -> None:
    """Une transition générique n'est pas confondue avec un fait métier."""

    response = product_details_response()
    claims = build_expected_claims(response)
    content = json.loads(generated_json(claims))
    content["segments"].insert(
        0,
        {
            "type": "natural",
            "text": (
                "Voici les informations disponibles sur ce produit."
            ),
        },
    )
    client = FakeCompletionClient(
        json.dumps(content, ensure_ascii=False)
    )

    result = await AnswerGenerator(client, 800).generate(
        "Donne-moi les détails du produit 4.",
        response,
        ProductDetailsIntent(product_id=4),
    )

    assert result.startswith(
        "Voici les informations disponibles sur ce produit."
    )


@pytest.mark.parametrize(
    "unclaimed_fact",
    [
        "Ce produit est disponible.",
        "Ce produit coûte cher.",
        "Ce produit est en stock.",
        "On peut le trouver facilement.",
    ],
)
async def test_rejects_business_assertion_in_natural_segment(
    unclaimed_fact: str,
) -> None:
    """Une transition ne peut pas contourner les claims structurés."""

    response = product_details_response()
    claims = build_expected_claims(response)
    content = json.loads(generated_json(claims))
    content["segments"].insert(
        0,
        {
            "type": "natural",
            "text": unclaimed_fact,
        },
    )
    client = FakeCompletionClient(
        json.dumps(content, ensure_ascii=False)
    )

    with pytest.raises(GeneratedAnswerError):
        await AnswerGenerator(client, 800).generate(
            "Donne-moi les détails du produit 4.",
            response,
            ProductDetailsIntent(product_id=4),
        )


@pytest.mark.parametrize(
    "response",
    [
        product_list_response(),
        stock_response(),
        branch_stock_response(),
        shopping_response(),
    ],
    ids=[
        "product-list",
        "stock-by-product",
        "stock-by-branch",
        "shopping-list",
    ],
)
async def test_accepts_complete_claims_for_each_business_response(
    response,
) -> None:
    """Valide les relations complètes des quatre autres réponses métier."""

    claims = build_expected_claims(response)
    client = FakeCompletionClient(generated_json(claims))

    result = await AnswerGenerator(client, 1200).generate(
        "Question métier",
        response,
    )

    assert result
    assert len(client.calls) == 1


async def test_rejects_prices_permuted_between_products() -> None:
    """Un bon ensemble de nombres ne suffit pas si les relations changent."""

    response = product_list_response()
    expected = build_expected_claims(response)
    summary, first, second = expected
    assert isinstance(first, ProductPriceClaim)
    assert isinstance(second, ProductPriceClaim)
    permuted = [
        summary,
        first.model_copy(update={"unit_price": second.unit_price}),
        second.model_copy(update={"unit_price": first.unit_price}),
    ]
    client = FakeCompletionClient(generated_json(permuted))

    with pytest.raises(GeneratedAnswerError):
        await AnswerGenerator(client, 800).generate(
            "Liste les produits.",
            response,
        )


@pytest.mark.parametrize("field", ["quantity", "branch_name"])
async def test_rejects_stock_relations_permuted_between_branches(
    field: str,
) -> None:
    """Refuse l'échange d'une quantité ou d'une branche entre deux lignes."""

    response = stock_response()
    expected = build_expected_claims(response)
    summary, first, second = expected
    assert isinstance(first, ProductAvailabilityClaim)
    assert isinstance(second, ProductAvailabilityClaim)
    permuted = [
        summary,
        first.model_copy(
            update={field: getattr(second, field)}
        ),
        second.model_copy(
            update={field: getattr(first, field)}
        ),
    ]
    client = FakeCompletionClient(generated_json(permuted))

    with pytest.raises(GeneratedAnswerError):
        await AnswerGenerator(client, 800).generate(
            "Où trouver le produit 7 ?",
            response,
            StockByProductIntent(product_id=7),
        )


@pytest.mark.parametrize(
    "mutation",
    ["added", "omitted", "duplicated"],
)
async def test_rejects_changed_claim_multiset(
    mutation: str,
) -> None:
    """Refuse tout ajout, oubli ou doublon dans les claims."""

    response = product_details_response()
    expected = build_expected_claims(response)
    claims = list(expected)
    if mutation == "added":
        claims.append(
            ProductPriceClaim(
                product_id=99,
                product_name="Produit inventé",
                unit_price=12.0,
                currency="EUR",
            )
        )
    elif mutation == "omitted":
        claims.clear()
    else:
        claims.append(expected[0])

    client = FakeCompletionClient(generated_json(claims))
    with pytest.raises(GeneratedAnswerError):
        await AnswerGenerator(client, 800).generate(
            "Détails du produit 4.",
            response,
        )


async def test_rejects_unavailable_claim_with_positive_quantity() -> None:
    """Le schéma refuse une indisponibilité associée à un stock positif."""

    response = stock_response()
    expected = build_expected_claims(response)
    payload = json.loads(generated_json(expected))
    availability = payload["segments"][1]["claim"]
    availability["available"] = False
    availability["quantity"] = 3
    client = FakeCompletionClient(
        json.dumps(payload, ensure_ascii=False)
    )

    with pytest.raises(GeneratedAnswerError):
        await AnswerGenerator(client, 800).generate(
            "Où trouver le produit 7 ?",
            response,
        )


async def test_rejects_negative_text_for_available_claim() -> None:
    """Le texte ne peut pas contredire un claim disponible."""

    response = stock_response()
    expected = build_expected_claims(response)
    assert isinstance(expected[1], ProductAvailabilityClaim)
    contradictory = (
        "Le produit 7 n'est pas disponible dans la branche "
        "Toulouse malgré 3 unités."
    )
    client = FakeCompletionClient(
        generated_json(
            expected,
            text_overrides={1: contradictory},
        )
    )

    with pytest.raises(GeneratedAnswerError):
        await AnswerGenerator(client, 800).generate(
            "Où trouver le produit 7 ?",
            response,
        )


@pytest.mark.parametrize(
    "leak",
    [
        "Consultez https://internal.example.",
        "La valeur NVIDIA_API_KEY est cachée.",
        "Le résultat vient du MCP.",
        "Authorization: Bearer valeur-secrète.",
        "Une requête PostgreSQL confirme ce résultat.",
    ],
)
async def test_rejects_secret_url_or_technical_leak(
    leak: str,
) -> None:
    """Un claim exact n'autorise jamais les marqueurs internes."""

    response = product_details_response()
    expected = build_expected_claims(response)
    text = f"{fact_text(expected[0])} {leak}"
    client = FakeCompletionClient(
        generated_json(expected, text_overrides={0: text})
    )

    with pytest.raises(GeneratedAnswerError):
        await AnswerGenerator(client, 800).generate(
            "Détails du produit 4.",
            response,
        )


async def test_maps_expected_provider_error_to_generation_error() -> None:
    """Une panne fournisseur attendue déclenche le fallback appelant."""

    response = product_details_response()
    client = FakeCompletionClient(
        error=NVIDIAConnectionError("network")
    )

    with pytest.raises(GeneratedAnswerError):
        await AnswerGenerator(client, 800).generate(
            "Détails du produit 4.",
            response,
        )


async def test_does_not_mask_unexpected_python_error() -> None:
    """Un bug inattendu reste visible au lieu d'être silencieusement caché."""

    response = product_details_response()
    client = FakeCompletionClient(
        error=RuntimeError("programming bug")
    )

    with pytest.raises(RuntimeError, match="programming bug"):
        await AnswerGenerator(client, 800).generate(
            "Détails du produit 4.",
            response,
        )


class ProductDetailsResolver:
    """Retourne une intention stable pour le test d'orchestration."""

    async def resolve(self, _question, _state=None):
        return ProductDetailsIntent(product_id=4)


class ProductDetailsClient:
    """Simule l'unique lecture MCP autorisée."""

    is_ready = True

    def __init__(self) -> None:
        self.calls = 0

    async def ensure_connected(self) -> bool:
        return True

    async def get_product_details(self, _product_id: int):
        self.calls += 1
        return ProductDetailsData(product=product_data())


class FailingAnswerGenerator:
    """Simule une sortie modèle invalide après la lecture métier."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        _question,
        _response,
        _intent=None,
        _history=None,
        _state=None,
    ):
        self.calls += 1
        raise GeneratedAnswerError("invalid claims")


async def test_orchestrator_keeps_builder_fallback_on_invalid_generation(
    caplog,
) -> None:
    """Une génération rejetée conserve la réponse déterministe complète."""

    client = ProductDetailsClient()
    generator = FailingAnswerGenerator()
    orchestrator = QueryOrchestrator(
        intent_classifier=ProductDetailsResolver(),
        client=client,
        answer_builder=AnswerBuilder(),
        answer_generator=generator,
    )

    response = await orchestrator.handle(
        QueryRequest(
            conversation_id=CONVERSATION_ID,
            question="Donne-moi les détails du produit 4.",
        )
    )

    assert response.type == "product_details"
    assert (
        validate_conversation_id(response.conversation_id)
        == response.conversation_id
    )
    assert response.answer == (
        "Le produit 4 est « Écran compact » et coûte 169,99 EUR."
    )
    assert client.calls == 1
    assert generator.calls == 1
    assert "fallback" in caplog.text
