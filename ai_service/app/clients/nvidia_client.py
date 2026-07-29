"""Client asynchrone partagé de MiniMax-M3 via l'API NVIDIA."""

from collections.abc import Callable, Sequence

import httpx

from app.errors import (
    NVIDIAAuthenticationError,
    NVIDIAConnectionError,
    NVIDIARateLimitError,
    NVIDIAResponseError,
    NVIDIAServiceError,
    NVIDIATimeoutError,
)


ChatMessage = dict[str, str]
HTTPClientFactory = Callable[..., httpx.AsyncClient]


class NVIDIAClient:
    """Partage un transport HTTP sans mémoire ni tool calling."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        request_timeout_seconds: float,
        client_factory: HTTPClientFactory = httpx.AsyncClient,
    ) -> None:
        """Construit un seul transport vers Chat Completions."""

        self._model = model
        self._endpoint = (
            f"{base_url.rstrip('/')}/chat/completions"
        )
        self._api_key = api_key
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
            "max_tokens": max_tokens,
            "stream": False,
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
            raise NVIDIATimeoutError(
                "Le délai du fournisseur IA est dépassé."
            ) from error
        except httpx.RequestError as error:
            raise NVIDIAConnectionError(
                "Le fournisseur IA n'est pas joignable."
            ) from error

        if response.status_code == 401:
            raise NVIDIAAuthenticationError(
                "Le fournisseur IA a refusé l'authentification."
            )

        if response.status_code == 429:
            raise NVIDIARateLimitError(
                "Le fournisseur IA limite temporairement les requêtes."
            )

        if not response.is_success:
            raise NVIDIAServiceError(
                "Le fournisseur IA a retourné une erreur."
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise NVIDIAResponseError(
                "La réponse du fournisseur IA est invalide."
            ) from error

        if not isinstance(payload, dict):
            raise NVIDIAResponseError(
                "La réponse du fournisseur IA est invalide."
            )

        choices = payload.get("choices")

        if not isinstance(choices, list) or len(choices) != 1:
            raise NVIDIAResponseError(
                "La réponse du fournisseur IA est invalide."
            )

        choice = choices[0]

        if not isinstance(choice, dict):
            raise NVIDIAResponseError(
                "La réponse du fournisseur IA est invalide."
            )

        message = choice.get("message")

        if not isinstance(message, dict):
            raise NVIDIAResponseError(
                "La réponse du fournisseur IA est invalide."
            )

        tool_calls = message.get("tool_calls")
        function_call = message.get("function_call")
        content = message.get("content")

        if tool_calls or function_call:
            raise NVIDIAResponseError(
                "Le fournisseur IA a tenté un appel d'outil interdit."
            )

        if not isinstance(content, str) or not content.strip():
            raise NVIDIAResponseError(
                "La réponse du fournisseur IA est vide."
            )

        return content

    async def aclose(self) -> None:
        """Ferme proprement le transport HTTP partagé."""

        await self._client.aclose()
