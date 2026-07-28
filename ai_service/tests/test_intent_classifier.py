"""Tests de sécurité et de contrat du classifieur conversationnel unique."""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from app.errors import (
    MiniMaxConnectionError,
    MiniMaxResponseError,
    MiniMaxTimeoutError,
)
from app.models.conversation import ConversationState, ConversationTurn
from app.models.intents import (
    ProductDetailsIntent,
    ProductListIntent,
    QueryIntent,
    StockByProductIntent,
    UnsupportedIntent,
)
from app.services.context_resolver import ContextResolver
from app.services.intent_classifier import IntentClassifier


pytestmark = pytest.mark.asyncio


class RecordingCompletionClient:
    """Retourne une sortie contrôlée et conserve le prompt exact."""

    def __init__(self, outcome: str | BaseException) -> None:
        self.outcome = outcome
        self.calls: list[tuple[Sequence[dict[str, str]], int]] = []

    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        max_tokens: int,
    ) -> str:
        self.calls.append((messages, max_tokens))

        if isinstance(self.outcome, BaseException):
            raise self.outcome

        return self.outcome


class RecordingFallback:
    """Retourne une intention sûre et compte chaque repli local."""

    def __init__(self, intent: QueryIntent) -> None:
        self.intent = intent
        self.questions: list[str] = []

    async def resolve(self, question: str) -> QueryIntent:
        self.questions.append(question)
        return self.intent


def _classifier(
    client: RecordingCompletionClient | None,
    fallback: RecordingFallback | None = None,
    *,
    max_tokens: int = 600,
) -> IntentClassifier:
    """Assemble le classifieur avec le validateur Python réel."""

    return IntentClassifier(
        model_client=client,
        fallback=fallback,
        context_resolver=ContextResolver(),
        max_tokens=max_tokens,
    )


async def test_valid_json_uses_exactly_one_model_call() -> None:
    """Une compréhension distante n'est jamais répétée dans le même tour."""

    client = RecordingCompletionClient(
        '{"intent":"product_details","product_id":11}'
    )
    classifier = _classifier(client, max_tokens=321)

    intent = await classifier.resolve(
        "Donne-moi les détails du produit 11.",
        ConversationState(),
    )

    assert intent == ProductDetailsIntent(product_id=11)
    assert len(client.calls) == 1
    assert client.calls[0][1] == 321


async def test_absent_model_uses_simple_fallback_with_zero_model_call() -> None:
    """Le mode local reste fonctionnel sans fournisseur distant."""

    fallback = RecordingFallback(
        ProductDetailsIntent(product_id=7)
    )
    classifier = _classifier(None, fallback)

    intent = await classifier.resolve(
        "Détails du produit 7.",
        ConversationState(),
    )

    assert intent == ProductDetailsIntent(product_id=7)
    assert fallback.questions == ["Détails du produit 7."]


@pytest.mark.parametrize(
    ("question", "reason_code"),
    [
        ("Et quelle est la météo ?", "out_of_domain"),
        ("Ajoute cinq unités au produit 11.", "read_only"),
    ],
)
async def test_local_guards_skip_model_entirely(
    question: str,
    reason_code: str,
) -> None:
    """Le hors domaine et les écritures sont terminaux avant MiniMax."""

    client = RecordingCompletionClient(
        '{"intent":"product_details","product_id":11}'
    )
    classifier = _classifier(client)

    intent = await classifier.resolve(
        question,
        ConversationState(
            last_intent="stock_by_product",
            last_product_id=11,
        ),
    )

    assert isinstance(intent, UnsupportedIntent)
    assert intent.reason_code == reason_code
    assert client.calls == []


@pytest.mark.parametrize(
    "invalid_json",
    [
        "```json\n{\"intent\":\"product_details\",\"product_id\":7}\n```",
        (
            '{"intent":"product_details","product_id":7,'
            '"unexpected":"forbidden"}'
        ),
        '{"intent":"product_details","product_id":true}',
        '{"intent":"product_details"}',
        '{"intent":"product_list","limit":0,"offset":0}',
        '{"intent":"product_list","limit":20,"offset":-1}',
        (
            '{"intent":"shopping_list","items":['
            '{"product_id":7,"quantity":1,"extra":true}]}'
        ),
        '{"intent":"unsupported"}',
    ],
)
async def test_invalid_or_non_strict_json_uses_validated_fallback(
    invalid_json: str,
) -> None:
    """Refuse coercitions, Markdown, champs supplémentaires et omissions."""

    client = RecordingCompletionClient(invalid_json)
    fallback = RecordingFallback(
        ProductDetailsIntent(product_id=7)
    )
    classifier = _classifier(client, fallback)

    intent = await classifier.resolve(
        "Détails du produit 7.",
        ConversationState(),
    )

    assert intent == ProductDetailsIntent(product_id=7)
    assert len(client.calls) == 1
    assert fallback.questions == ["Détails du produit 7."]


async def test_prompt_contains_strict_bounded_parameter_schema() -> None:
    """Expose au modèle les contraintes réellement revalidées par Pydantic."""

    client = RecordingCompletionClient(
        '{"intent":"product_list","limit":5,"offset":0}'
    )
    classifier = _classifier(client)

    intent = await classifier.resolve(
        "Montre-moi les cinq premiers produits.",
        ConversationState(),
    )

    assert intent == ProductListIntent(limit=5, offset=0)
    messages, _max_tokens = client.calls[0]
    assert [message["role"] for message in messages] == [
        "system",
        "user",
    ]
    payload = json.loads(messages[1]["content"])
    schema = payload["schema_sortie"]
    properties = schema["properties"]

    assert schema["additionalProperties"] is False
    assert properties["product_id"]["anyOf"][0][
        "exclusiveMinimum"
    ] == 0
    assert properties["branch_id"]["anyOf"][0][
        "exclusiveMinimum"
    ] == 0
    assert properties["limit"]["anyOf"][0] == {
        "maximum": 100,
        "minimum": 1,
        "type": "integer",
    }
    assert properties["offset"]["anyOf"][0]["minimum"] == 0
    assert properties["items"]["maxItems"] == 100
    item_schema = schema["$defs"]["ShoppingListItem"]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["required"]) == {
        "product_id",
        "quantity",
    }


async def test_explicit_product_and_branch_survive_model_omission() -> None:
    """Le validateur réinjecte Toulouse si le modèle oublie la contrainte."""

    client = RecordingCompletionClient(
        '{"intent":"stock_by_product","product_id":11}'
    )
    classifier = _classifier(client)

    intent = await classifier.resolve(
        "Le produit 11 est-il disponible à Toulouse ?",
        ConversationState(),
    )

    assert intent == StockByProductIntent(
        product_id=11,
        branch_name="Toulouse",
    )
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    ("question", "model_json"),
    [
        (
            "Où est disponible le produit 11 ?",
            '{"intent":"stock_by_product","product_id":99}',
        ),
        (
            "Stock de la branche 3.",
            '{"intent":"stock_by_branch","branch_id":4}',
        ),
        (
            "Je cherche deux produits 4 et un produit 8.",
            (
                '{"intent":"shopping_list","items":['
                '{"product_id":4,"quantity":9},'
                '{"product_id":8,"quantity":1}]}'
            ),
        ),
    ],
)
async def test_python_anchor_rejects_invented_business_parameters(
    question: str,
    model_json: str,
) -> None:
    """Bloque IDs, branches et quantités qui contredisent la question."""

    client = RecordingCompletionClient(model_json)
    classifier = _classifier(client)

    intent = await classifier.resolve(
        question,
        ConversationState(),
    )

    assert isinstance(intent, UnsupportedIntent)
    assert intent.reason_code == "ambiguous"
    assert len(client.calls) == 1


async def test_python_anchor_replaces_invented_branch_with_explicit_one() -> None:
    """Carcassonne proposée ne peut pas remplacer Toulouse écrite."""

    client = RecordingCompletionClient(
        (
            '{"intent":"stock_by_product","product_id":11,'
            '"branch_name":"Carcassonne"}'
        )
    )
    classifier = _classifier(client)

    intent = await classifier.resolve(
        "Le produit 11 est-il disponible à Toulouse ?",
        ConversationState(),
    )

    assert intent == StockByProductIntent(
        product_id=11,
        branch_name="Toulouse",
    )
    assert len(client.calls) == 1


async def test_compact_shopping_list_syntax_is_not_catalog_request() -> None:
    """Reconnaît « 12 x2, 7 x1 » comme une liste quantifiée."""

    classifier = _classifier(None)

    intent = await classifier.resolve(
        "Vérifie la liste : 12 x2, 7 x1.",
        ConversationState(),
    )

    assert intent.type == "shopping_list"
    assert [item.model_dump() for item in intent.items] == [
        {"product_id": 12, "quantity": 2},
        {"product_id": 7, "quantity": 1},
    ]


async def test_missing_branch_is_clarification_not_product_list() -> None:
    """Le mot « montre » ne doit pas gagner sur un stock incomplet."""

    classifier = _classifier(None)

    intent = await classifier.resolve(
        "Montre-moi le stock de la branche.",
        ConversationState(),
    )

    assert isinstance(intent, UnsupportedIntent)
    assert intent.reason_code == "missing_branch_id"


@pytest.mark.parametrize(
    "question",
    [
        "stock du produit 11",
        "stock du produits 11",
        "stock de l’article 11",
        "stock de la référence 11",
    ],
)
async def test_product_stock_never_invents_branch_from_product_phrase(
    question: str,
) -> None:
    """Ne transforme pas le complément produit en nom de branche."""

    classifier = _classifier(None)

    intent = await classifier.resolve(
        question,
        ConversationState(),
    )

    assert intent == StockByProductIntent(product_id=11)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "stock de Toulouse",
            {
                "type": "stock_by_branch",
                "branch_name": "Toulouse",
            },
        ),
        (
            "détails des 10 premiers produits",
            {
                "type": "product_list",
                "limit": 10,
                "offset": 0,
            },
        ),
        (
            "détails du produit 10",
            {
                "type": "product_details",
                "product_id": 10,
            },
        ),
        (
            "liste les produits de la branche Carcassonne",
            {
                "type": "stock_by_branch",
                "branch_name": "Carcassonne",
            },
        ),
    ],
)
async def test_required_isolated_fallback_regressions(
    question: str,
    expected: dict[str, object],
) -> None:
    """Conserve les formulations exigées sans modèle disponible."""

    classifier = _classifier(None)

    intent = await classifier.resolve(
        question,
        ConversationState(),
    )

    assert intent.model_dump(exclude_none=True) == expected


async def test_prompt_bounds_history_and_redacts_every_untrusted_string() -> None:
    """N'envoie ni historique illimité, ni URL, ni valeur sensible."""

    turns = [
        ConversationTurn(
            user=(
                f"tour {index} api_key=dummy-secret-{index} "
                f"https://internal.example/{index}"
            ),
            assistant=(
                f"réponse {index} token=dummy-token-{index}"
            ),
        )
        for index in range(12)
    ]
    state = ConversationState(
        turns=turns,
        last_intent="stock_by_product",
        last_product_id=11,
        last_branch_name=(
            "https://internal.example api_key=state-secret"
        ),
        last_stock_branches=[
            {
                "branch_id": 2,
                "branch_name": "token=branch-secret",
                "quantity": 10,
            }
        ],
    )
    client = RecordingCompletionClient(
        '{"intent":"stock_by_product","product_id":11}'
    )
    classifier = _classifier(client)
    question = (
        "Produit 11 Authorization: Bearer "
        "abcdefghijklmno https://private.example/" + "x" * 2500
    )

    await classifier.resolve(question, state)

    messages, _max_tokens = client.calls[0]
    payload = json.loads(messages[1]["content"])
    history = payload["historique_recent_non_fiable"]
    serialized = json.dumps(payload, ensure_ascii=False)

    assert len(history) == 10
    assert history[0]["user"].startswith("tour 2 ")
    assert history[-1]["user"].startswith("tour 11 ")
    assert len(payload["question_courante_non_fiable"]) <= 2000
    assert "dummy-secret" not in serialized
    assert "dummy-token" not in serialized
    assert "state-secret" not in serialized
    assert "branch-secret" not in serialized
    assert "abcdefghijklmno" not in serialized
    assert "https://" not in serialized
    assert "[donnée sensible masquée]" in serialized


@pytest.mark.parametrize(
    "expected_error",
    [
        MiniMaxTimeoutError("timeout"),
        MiniMaxConnectionError("offline"),
        MiniMaxResponseError("invalid response"),
    ],
)
async def test_expected_model_failure_falls_back_to_simple_question(
    expected_error: BaseException,
) -> None:
    """Une panne distante prévue ne produit pas d'erreur interne."""

    client = RecordingCompletionClient(expected_error)
    classifier = _classifier(client)

    intent = await classifier.resolve(
        "Détails du produit 7.",
        ConversationState(),
    )

    assert intent == ProductDetailsIntent(product_id=7)
    assert len(client.calls) == 1


async def test_unexpected_python_bug_is_not_silently_masked() -> None:
    """Laisse remonter un défaut de programmation étranger aux pannes prévues."""

    client = RecordingCompletionClient(
        RuntimeError("unexpected classifier bug")
    )
    classifier = _classifier(client)

    with pytest.raises(
        RuntimeError,
        match="unexpected classifier bug",
    ):
        await classifier.resolve(
            "Détails du produit 7.",
            ConversationState(),
        )

    assert len(client.calls) == 1
