"""Tests HTTP du classificateur Ollama sans réseau réel."""

import json
from typing import Any

import httpx
import pytest

from app.errors import (
    IntentClassifierResponseError,
    IntentClassifierTimeoutError,
    IntentClassifierUnavailableError,
)
from app.models.intents import (
    ProductDetailsIntent,
    ProductListIntent,
    ShoppingListIntent,
    StockByBranchIntent,
    StockByProductIntent,
    UnsupportedIntent,
)
from app.services.ollama_classifier import (
    INTENT_JSON_SCHEMA,
    SYSTEM_MESSAGE,
    OllamaIntentClassifier,
)


pytestmark = pytest.mark.asyncio


def chat_response(intent: dict[str, object]) -> dict[str, object]:
    """Construit une enveloppe conforme à l'API Ollama."""

    return {
        "model": "gemma3:latest",
        "created_at": "2026-07-26T12:00:00Z",
        "message": {
            "role": "assistant",
            "content": json.dumps(intent),
        },
        "done": True,
        "done_reason": "stop",
        "total_duration": 10,
        "load_duration": 1,
        "prompt_eval_count": 20,
        "prompt_eval_duration": 2,
        "eval_count": 10,
        "eval_duration": 3,
    }


def create_classifier(
    handler: Any,
) -> tuple[OllamaIntentClassifier, httpx.AsyncClient]:
    """Relie le fournisseur à un transport HTTP contrôlé."""

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )
    classifier = OllamaIntentClassifier(
        http_client=http_client,
        base_url="http://ollama.test:11434/",
        model="gemma3:latest",
        request_timeout_seconds=2.5,
    )

    return classifier, http_client


async def test_classifier_sends_exact_structured_request() -> None:
    """Envoie uniquement le schéma, les instructions et la question."""

    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request

        return httpx.Response(
            200,
            json=chat_response(
                {
                    "type": "product_details",
                    "product_id": 12,
                }
            ),
        )

    classifier, http_client = create_classifier(handler)

    try:
        intent = await classifier.classify(
            "Peux-tu me décrire le produit 12 ?"
        )
    finally:
        await http_client.aclose()

    assert intent == ProductDetailsIntent(product_id=12)
    assert captured_request is not None
    assert captured_request.method == "POST"
    assert str(captured_request.url) == (
        "http://ollama.test:11434/api/chat"
    )

    payload = json.loads(captured_request.content)

    assert payload["model"] == "gemma3:latest"
    assert payload["stream"] is False
    assert payload["format"] == INTENT_JSON_SCHEMA
    assert payload["options"] == {
        "temperature": 0,
    }
    assert payload["messages"] == [
        {
            "role": "system",
            "content": SYSTEM_MESSAGE,
        },
        {
            "role": "user",
            "content": "Peux-tu me décrire le produit 12 ?",
        },
    ]
    assert "tools" not in payload
    timeout = captured_request.extensions["timeout"]
    assert set(timeout.values()) == {
        2.5,
    }
    assert "sans répondre à la question" in SYSTEM_MESSAGE
    assert "N'invente jamais" in SYSTEM_MESSAGE
    assert "uniquement les nombres" in SYSTEM_MESSAGE
    assert "unsupported" in SYSTEM_MESSAGE
    assert "contradictoire" in SYSTEM_MESSAGE
    assert "nom de produit en identifiant" in SYSTEM_MESSAGE
    assert "Conserve les doublons" in SYSTEM_MESSAGE
    assert "product-mcp-server" not in (
        captured_request.content.decode()
    )
    assert http_client.is_closed is True


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            {
                "type": "product_list",
                "limit": 10,
                "offset": 0,
            },
            ProductListIntent,
        ),
        (
            {
                "type": "product_details",
                "product_id": 12,
            },
            ProductDetailsIntent,
        ),
        (
            {
                "type": "stock_by_product",
                "product_id": 12,
            },
            StockByProductIntent,
        ),
        (
            {
                "type": "stock_by_branch",
                "branch_id": 3,
            },
            StockByBranchIntent,
        ),
        (
            {
                "type": "shopping_list",
                "items": [
                    {
                        "product_id": 12,
                        "quantity": 2,
                    }
                ],
            },
            ShoppingListIntent,
        ),
        (
            {
                "type": "unsupported",
                "reason": "Demande ambiguë.",
            },
            UnsupportedIntent,
        ),
    ],
)
async def test_classifier_validates_each_existing_intent(
    payload: dict[str, object],
    expected_type: type[object],
) -> None:
    """Retourne uniquement une variante de l'union existante."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=chat_response(payload),
        )

    classifier, http_client = create_classifier(handler)

    try:
        intent = await classifier.classify("question validée")
    finally:
        await http_client.aclose()

    assert isinstance(intent, expected_type)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(
            200,
            content=b"not-json",
        ),
        httpx.Response(
            200,
            json={},
        ),
        httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                },
            },
        ),
        httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": 12,
                },
            },
        ),
        httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "not-json",
                },
            },
        ),
        httpx.Response(
            200,
            json=chat_response(
                {
                    "type": "product_details",
                    "product_id": 12,
                    "extra": True,
                }
            ),
        ),
        httpx.Response(
            200,
            json=chat_response(
                {
                    "type": "product_details",
                    "product_id": 0,
                }
            ),
        ),
        httpx.Response(
            200,
            json={
                **chat_response(
                    {
                        "type": "product_details",
                        "product_id": 12,
                    }
                ),
                "unexpected": True,
            },
        ),
        httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "type": "product_details",
                            "product_id": 12,
                        }
                    ),
                    "tool_calls": [],
                },
            },
        ),
    ],
)
async def test_classifier_rejects_invalid_responses(
    response: httpx.Response,
) -> None:
    """Traduit les enveloppes et intentions invalides en erreur locale."""

    def handler(request: httpx.Request) -> httpx.Response:
        response.request = request
        return response

    classifier, http_client = create_classifier(handler)

    try:
        with pytest.raises(IntentClassifierResponseError):
            await classifier.classify("question")
    finally:
        await http_client.aclose()


async def test_classifier_rejects_invalid_http_status() -> None:
    """Ne laisse pas traverser HTTPStatusError."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={
                "error": "technical details",
            },
        )

    classifier, http_client = create_classifier(handler)

    try:
        with pytest.raises(
            IntentClassifierResponseError
        ) as exception:
            await classifier.classify("question")
    finally:
        await http_client.aclose()

    assert "technical details" not in str(exception.value)


async def test_classifier_translates_timeout() -> None:
    """Ne laisse pas traverser le timeout httpx."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "technical timeout",
            request=request,
        )

    classifier, http_client = create_classifier(handler)

    try:
        with pytest.raises(
            IntentClassifierTimeoutError
        ) as exception:
            await classifier.classify("question")
    finally:
        await http_client.aclose()

    assert "technical timeout" not in str(exception.value)


async def test_classifier_translates_connection_error() -> None:
    """Ne laisse pas traverser une indisponibilité httpx."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "technical connection",
            request=request,
        )

    classifier, http_client = create_classifier(handler)

    try:
        with pytest.raises(
            IntentClassifierUnavailableError
        ) as exception:
            await classifier.classify("question")
    finally:
        await http_client.aclose()

    assert "technical connection" not in str(exception.value)
