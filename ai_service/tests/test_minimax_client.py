"""Tests sans réseau du client MiniMax compatible OpenAI."""

import json
from typing import Any

import httpx
import pytest

from app.clients.minimax_client import MiniMaxClient
from app.errors import (
    MiniMaxAuthenticationError,
    MiniMaxConnectionError,
    MiniMaxRateLimitError,
    MiniMaxResponseError,
    MiniMaxServiceError,
    MiniMaxTimeoutError,
)


pytestmark = pytest.mark.asyncio
SECRET = "test-secret-never-log"


def completion_response(
    content: str = '{"answer":"Bonjour."}',
    *,
    tool_calls: list[dict[str, object]] | None = None,
    function_call: dict[str, object] | None = None,
) -> dict[str, object]:
    """Construit une enveloppe Chat Completions minimale."""

    message: dict[str, object] = {
        "role": "assistant",
        "content": content,
    }

    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    if function_call is not None:
        message["function_call"] = function_call

    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "MiniMax-M3",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
            }
        ],
    }


class HTTPFactory:
    """Injecte un MockTransport au client HTTP réellement utilisé."""

    def __init__(self, handler: Any) -> None:
        """Conserve le handler et les paramètres observables."""

        self.handler = handler
        self.calls: list[dict[str, object]] = []
        self.http_clients: list[httpx.AsyncClient] = []

    def __call__(self, **configuration: object) -> httpx.AsyncClient:
        """Crée un transport local avec la configuration observée."""

        self.calls.append(configuration)
        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler),
            **configuration,
        )
        self.http_clients.append(http_client)

        return http_client


def create_client(handler: Any) -> tuple[MiniMaxClient, HTTPFactory]:
    """Construit le client testé sans sortie réseau."""

    factory = HTTPFactory(handler)
    client = MiniMaxClient(
        api_key=SECRET,
        base_url="https://minimax.test/v1/",
        model="MiniMax-M3",
        request_timeout_seconds=3,
        client_factory=factory,
    )

    return client, factory


async def test_complete_sends_no_tools_and_returns_content() -> None:
    """Utilise Chat Completions sans exposer de mécanisme d'outil."""

    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            200,
            json=completion_response('{"answer":"Bonjour."}'),
        )

    client, factory = create_client(handler)

    try:
        result = await client.complete(
            [
                {
                    "role": "user",
                    "content": "Question",
                }
            ],
            max_tokens=600,
        )
    finally:
        await client.aclose()

    assert result == '{"answer":"Bonjour."}'
    assert len(factory.calls) == 1
    assert factory.calls[0] == {
        "timeout": 3,
    }
    assert captured is not None
    assert str(captured.url) == (
        "https://minimax.test/v1/chat/completions"
    )
    body = json.loads(captured.content)
    assert captured.headers["Authorization"] == f"Bearer {SECRET}"
    assert body["model"] == "MiniMax-M3"
    assert body["max_completion_tokens"] == 600
    assert body["stream"] is False
    assert body["reasoning_split"] is True
    assert "tools" not in body
    assert "tool_choice" not in body
    assert factory.http_clients[0].is_closed is True


async def test_complete_supports_nvidia_token_contract() -> None:
    """Réutilise le client unique avec le contrat NVIDIA MiniMax-M3."""

    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            200,
            json=completion_response('{"intent":"product_list"}'),
        )

    factory = HTTPFactory(handler)
    client = MiniMaxClient(
        api_key=SECRET,
        base_url="https://integrate.api.nvidia.test/v1",
        model="minimaxai/minimax-m3",
        request_timeout_seconds=3,
        client_factory=factory,
        token_parameter="max_tokens",
        additional_payload={},
    )

    try:
        result = await client.complete(
            [{"role": "user", "content": "Question"}],
            max_tokens=700,
        )
    finally:
        await client.aclose()

    assert result == '{"intent":"product_list"}'
    assert captured is not None
    body = json.loads(captured.content)
    assert body["max_tokens"] == 700
    assert "max_completion_tokens" not in body
    assert "reasoning_split" not in body
    assert "tools" not in body
    assert "tool_choice" not in body


@pytest.mark.parametrize(
    ("handler_error", "expected_error"),
    [
        (
            httpx.ReadTimeout(
                "timeout",
                request=httpx.Request(
                    "POST",
                    "https://minimax.test/v1/chat/completions",
                ),
            ),
            MiniMaxTimeoutError,
        ),
        (
            httpx.ConnectError(
                "network",
                request=httpx.Request(
                    "POST",
                    "https://minimax.test/v1/chat/completions",
                ),
            ),
            MiniMaxConnectionError,
        ),
    ],
)
async def test_complete_maps_transport_errors(
    handler_error: Exception,
    expected_error: type[Exception],
) -> None:
    """Transforme timeout et réseau en erreurs locales nettoyées."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise handler_error

    client, _factory = create_client(handler)

    try:
        with pytest.raises(expected_error):
            await client.complete([], max_tokens=20)
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, MiniMaxAuthenticationError),
        (429, MiniMaxRateLimitError),
        (500, MiniMaxServiceError),
    ],
)
async def test_complete_maps_http_errors_without_secret(
    status_code: int,
    expected_error: type[Exception],
    caplog,
) -> None:
    """Ne propage ni réponse brute ni clé dans une erreur HTTP."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={
                "error": {
                    "message": f"remote body {SECRET}",
                    "type": "remote_error",
                    "code": "remote_error",
                }
            },
        )

    client, _factory = create_client(handler)

    try:
        with pytest.raises(expected_error) as raised:
            await client.complete([], max_tokens=20)
    finally:
        await client.aclose()

    assert SECRET not in str(raised.value)
    assert SECRET not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        {
            **completion_response(),
            "choices": [],
        },
        completion_response(""),
        completion_response(
            "",
            tool_calls=[
                {
                    "id": "call-test",
                    "type": "function",
                    "function": {
                        "name": "forbidden",
                        "arguments": "{}",
                    },
                }
            ],
        ),
        completion_response(
            "",
            function_call={
                "name": "forbidden",
                "arguments": "{}",
            },
        ),
    ],
)
async def test_complete_rejects_invalid_or_tool_call_response(
    payload: dict[str, object],
) -> None:
    """Refuse une sortie vide, sans choix ou contenant un tool call."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client, _factory = create_client(handler)

    try:
        with pytest.raises(MiniMaxResponseError):
            await client.complete([], max_tokens=20)
    finally:
        await client.aclose()
