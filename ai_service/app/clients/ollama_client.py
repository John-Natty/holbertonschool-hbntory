"""Transport JSON asynchrone partagé pour le modèle local Ollama."""

from collections.abc import Sequence

import httpx
from pydantic import ValidationError

from app.clients.minimax_client import ChatMessage
from app.errors import (
    MiniMaxConnectionError,
    MiniMaxResponseError,
    MiniMaxTimeoutError,
)
from app.models.data import (
    NonEmptyString,
    StrictModel,
    StrictString,
)


class _OllamaMessage(StrictModel):
    """Décrit le seul message utile d'une réponse `/api/chat`."""

    role: NonEmptyString
    content: StrictString


class _OllamaResponse(StrictModel):
    """Valide l'enveloppe minimale renvoyée par Ollama."""

    message: _OllamaMessage


class OllamaClient:
    """Expose le même contrat de complétion que le client MiniMax."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        base_url: str,
        model: str,
        request_timeout_seconds: float,
    ) -> None:
        """Conserve un transport partagé, sans logique métier."""

        self._http_client = http_client
        self._endpoint = f"{base_url.rstrip('/')}/api/chat"
        self._model = model
        self._request_timeout_seconds = request_timeout_seconds

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
    ) -> str:
        """Retourne uniquement un objet JSON textuel produit localement."""

        try:
            response = await self._http_client.post(
                self._endpoint,
                json={
                    "model": self._model,
                    "stream": False,
                    "format": "json",
                    "keep_alive": "10m",
                    "options": {
                        "temperature": 0,
                        "num_predict": max_tokens,
                    },
                    "messages": list(messages),
                },
                timeout=self._request_timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise MiniMaxTimeoutError(
                "Le délai du fournisseur IA est dépassé."
            ) from error
        except httpx.HTTPError as error:
            raise MiniMaxConnectionError(
                "Le fournisseur IA n'est pas joignable."
            ) from error

        if not response.is_success:
            raise MiniMaxResponseError(
                "Le fournisseur IA a retourné un statut invalide."
            )

        try:
            envelope = _OllamaResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise MiniMaxResponseError(
                "La réponse du fournisseur IA est invalide."
            ) from error

        if envelope.message.role != "assistant":
            raise MiniMaxResponseError(
                "La réponse du fournisseur IA est invalide."
            )

        content = envelope.message.content.strip()

        if not content:
            raise MiniMaxResponseError(
                "La réponse du fournisseur IA est vide."
            )

        return content
