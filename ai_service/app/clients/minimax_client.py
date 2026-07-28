"""Client asynchrone partagé de l'API MiniMax compatible OpenAI."""

from collections.abc import Callable, Mapping, Sequence
from typing import Literal

import httpx

from app.errors import (
    MiniMaxAuthenticationError,
    MiniMaxConnectionError,
    MiniMaxRateLimitError,
    MiniMaxResponseError,
    MiniMaxServiceError,
    MiniMaxTimeoutError,
)


ChatMessage = dict[str, str]
HTTPClientFactory = Callable[..., httpx.AsyncClient]
TokenParameter = Literal[
    "max_tokens",
    "max_completion_tokens",
]


class MiniMaxClient:
    """Partage un transport HTTP sans mémoire ni tool calling."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        request_timeout_seconds: float,
        client_factory: HTTPClientFactory = httpx.AsyncClient,
        token_parameter: TokenParameter = "max_completion_tokens",
        additional_payload: Mapping[str, object] | None = None,
    ) -> None:
        """Construit un seul transport vers Chat Completions."""

        self._model = model
        self._endpoint = (
            f"{base_url.rstrip('/')}/chat/completions"
        )
        self._api_key = api_key
        self._token_parameter = token_parameter
        self._additional_payload = dict(
            additional_payload
            if additional_payload is not None
            else {
                "reasoning_split": True,
            }
        )
        self._client = client_factory(
            timeout=request_timeout_seconds,
        )

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
    ) -> str:
        """Retourne uniquement le texte final d'une complétion."""

        payload: dict[str, object] = {
            "model": self._model,
            "messages": list(messages),
            self._token_parameter: max_tokens,
            "stream": False,
            **self._additional_payload,
        }

        try:
            response = await self._client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as error:
            raise MiniMaxTimeoutError(
                "Le délai du fournisseur IA est dépassé."
            ) from error
        except httpx.RequestError as error:
            raise MiniMaxConnectionError(
                "Le fournisseur IA n'est pas joignable."
            ) from error

        if response.status_code == 401:
            raise MiniMaxAuthenticationError(
                "Le fournisseur IA a refusé l'authentification."
            )

        if response.status_code == 429:
            raise MiniMaxRateLimitError(
                "Le fournisseur IA limite temporairement les requêtes."
            )

        if not response.is_success:
            raise MiniMaxServiceError(
                "Le fournisseur IA a retourné une erreur."
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise MiniMaxResponseError(
                "La réponse du fournisseur IA est invalide."
            ) from error

        if not isinstance(payload, dict):
            raise MiniMaxResponseError(
                "La réponse du fournisseur IA est invalide."
            )

        choices = payload.get("choices")

        if not isinstance(choices, list) or len(choices) != 1:
            raise MiniMaxResponseError(
                "La réponse du fournisseur IA est invalide."
            )

        choice = choices[0]

        if not isinstance(choice, dict):
            raise MiniMaxResponseError(
                "La réponse du fournisseur IA est invalide."
            )

        message = choice.get("message")

        if not isinstance(message, dict):
            raise MiniMaxResponseError(
                "La réponse du fournisseur IA est invalide."
            )

        tool_calls = message.get("tool_calls")
        function_call = message.get("function_call")
        content = message.get("content")

        if tool_calls or function_call:
            raise MiniMaxResponseError(
                "Le fournisseur IA a tenté un appel d'outil interdit."
            )

        if not isinstance(content, str) or not content.strip():
            raise MiniMaxResponseError(
                "La réponse du fournisseur IA est vide."
            )

        return content

    async def aclose(self) -> None:
        """Ferme proprement le transport HTTP partagé."""

        await self._client.aclose()
