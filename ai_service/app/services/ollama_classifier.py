"""Classificateur d'intention structuré utilisant l'API locale Ollama."""

from typing import Literal

import httpx
from pydantic import StrictBool, TypeAdapter, ValidationError

from app.errors import (
    IntentClassifierResponseError,
    IntentClassifierTimeoutError,
    IntentClassifierUnavailableError,
)
from app.models.data import (
    NonEmptyString,
    StrictModel,
    StrictNonNegativeInt,
    StrictString,
)
from app.models.intents import QueryIntent


INTENT_ADAPTER = TypeAdapter(QueryIntent)
INTENT_JSON_SCHEMA = INTENT_ADAPTER.json_schema()

SYSTEM_MESSAGE = (
    "Tu es uniquement un classificateur d'intentions. Retourne exactement "
    "une intention conforme au schéma JSON fourni, sans répondre à la "
    "question et sans ajouter de texte autour du JSON. N'invente jamais "
    "d'identifiant ni de quantité : utilise uniquement les nombres "
    "explicitement présents dans la question. Retourne unsupported si une "
    "information obligatoire manque ou si la demande est contradictoire. "
    "Ne transforme jamais un nom de produit en identifiant. Conserve les "
    "doublons d'une liste d'achats."
)


class OllamaMessage(StrictModel):
    """Décrit le message assistant utile d'une réponse Ollama."""

    role: Literal["assistant"]
    content: StrictString


class OllamaChatResponse(StrictModel):
    """Valide les champs connus de la réponse Ollama `/api/chat`."""

    message: OllamaMessage
    model: NonEmptyString | None = None
    created_at: NonEmptyString | None = None
    done: StrictBool | None = None
    done_reason: NonEmptyString | None = None
    total_duration: StrictNonNegativeInt | None = None
    load_duration: StrictNonNegativeInt | None = None
    prompt_eval_count: StrictNonNegativeInt | None = None
    prompt_eval_duration: StrictNonNegativeInt | None = None
    eval_count: StrictNonNegativeInt | None = None
    eval_duration: StrictNonNegativeInt | None = None


class OllamaIntentClassifier:
    """Classe une question sans accès aux données ou aux outils MCP."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
        model: str,
        request_timeout_seconds: float,
    ) -> None:
        """Injecte le client partagé et la configuration Ollama."""

        self._http_client = http_client
        self._endpoint = (
            f"{base_url.rstrip('/')}/api/chat"
        )
        self._model = model
        self._request_timeout_seconds = request_timeout_seconds

    async def classify(
        self,
        question: str,
    ) -> QueryIntent:
        """Demande une intention JSON puis la valide strictement."""

        try:
            response = await self._http_client.post(
                self._endpoint,
                json=self._request_payload(question),
                timeout=self._request_timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise IntentClassifierTimeoutError(
                "Le délai du classificateur est dépassé."
            ) from error
        except httpx.HTTPError as error:
            raise IntentClassifierUnavailableError(
                "Le classificateur n'est pas disponible."
            ) from error

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise IntentClassifierResponseError(
                "Le classificateur a retourné un statut invalide."
            ) from error

        try:
            payload = response.json()
            chat_response = OllamaChatResponse.model_validate(
                payload
            )
            return INTENT_ADAPTER.validate_json(
                chat_response.message.content
            )
        except (ValueError, ValidationError) as error:
            raise IntentClassifierResponseError(
                "La réponse du classificateur est invalide."
            ) from error

    def _request_payload(
        self,
        question: str,
    ) -> dict[str, object]:
        """Construit la requête sans donnée métier ni outil."""

        return {
            "model": self._model,
            "stream": False,
            "format": INTENT_JSON_SCHEMA,
            "options": {
                "temperature": 0,
            },
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_MESSAGE,
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
        }
