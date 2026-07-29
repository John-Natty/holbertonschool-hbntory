"""Tests sans réseau du client MiniMax-M3 via NVIDIA."""

import json
from typing import Any

import httpx
import pytest

from app.clients.nvidia_client import NVIDIAClient
from app.errors import (
    NVIDIAAuthenticationError,
    NVIDIAConnectionError,
    NVIDIARateLimitError,
    NVIDIAResponseError,
    NVIDIAServiceError,
    NVIDIATimeoutError,
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
        "model": "minimaxai/minimax-m3",
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


def create_client(handler: Any) -> tuple[NVIDIAClient, HTTPFactory]:
    """Construit le client testé sans sortie réseau."""

    factory = HTTPFactory(handler)
    client = NVIDIAClient(
        api_key=SECRET,
        base_url="https://integrate.api.nvidia.test/v1/",
        model="minimaxai/minimax-m3",
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
        "https://integrate.api.nvidia.test/v1/chat/completions"
    )
    body = json.loads(captured.content)
    assert captured.headers["Authorization"] == f"Bearer {SECRET}"
    assert body["model"] == "minimaxai/minimax-m3"
    assert body["max_tokens"] == 600
    assert body["stream"] is False
    assert "tools" not in body
    assert "tool_choice" not in body
    assert factory.http_clients[0].is_closed is True


@pytest.mark.parametrize(
    ("handler_error", "expected_error"),
    [
        (
            httpx.ReadTimeout(
                "timeout",
                request=httpx.Request(
                    "POST",
                    "https://integrate.api.nvidia.test/v1/chat/completions",
                ),
            ),
            NVIDIATimeoutError,
        ),
        (
            httpx.ConnectError(
                "network",
                request=httpx.Request(
                    "POST",
                    "https://integrate.api.nvidia.test/v1/chat/completions",
                ),
            ),
            NVIDIAConnectionError,
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
        (401, NVIDIAAuthenticationError),
        (429, NVIDIARateLimitError),
        (500, NVIDIAServiceError),
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
        with pytest.raises(NVIDIAResponseError):
            await client.complete([], max_tokens=20)
    finally:
        await client.aclose()
