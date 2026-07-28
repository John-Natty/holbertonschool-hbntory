"""Tests HTTP du contrat conversationnel public."""

import re

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError

from app.api.dependencies import get_query_orchestrator
from app.models.conversation import generate_conversation_id
from app.models.query import (
    ErrorDetail,
    ErrorResponse,
    QueryRequest,
    QueryResponse,
    UnsupportedResponse,
)


pytestmark = pytest.mark.asyncio


class RecordingConversationService:
    """Faux service qui conserve et restitue l'identifiant public."""

    def __init__(self) -> None:
        self.requests: list[QueryRequest] = []

    async def handle(
        self,
        request: QueryRequest,
    ) -> QueryResponse:
        """Simule la création d'une session puis sa réutilisation."""

        self.requests.append(request)
        conversation_id = (
            request.conversation_id
            or generate_conversation_id()
        )

        if request.question == "déclenche une erreur":
            return ErrorResponse(
                conversation_id=conversation_id,
                answer="Le service est temporairement indisponible.",
                error=ErrorDetail(
                    code="service_unavailable",
                    message="Le serveur MCP n’est pas connecté.",
                ),
            )

        return UnsupportedResponse(
            conversation_id=conversation_id,
            answer="La question a été traitée.",
        )


async def install_fake_service(
    application: FastAPI,
    service: RecordingConversationService,
) -> None:
    """Injecte un service asynchrone sans démarrer de dépendance réseau."""

    async def get_fake_service() -> RecordingConversationService:
        return service

    application.dependency_overrides[
        get_query_orchestrator
    ] = get_fake_service


async def test_first_request_creates_conversation_identifier(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Préserve la compatibilité d'une requête contenant seulement question."""

    service = RecordingConversationService()
    await install_fake_service(application, service)

    response = await client.post(
        "/api/query",
        json={
            "question": "Où est disponible le produit 11 ?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert re.fullmatch(
        r"[A-Za-z0-9_-]{32,64}",
        body["conversation_id"],
    )
    assert set(body) == {
        "conversation_id",
        "success",
        "answer",
        "type",
        "data",
        "error",
    }
    assert service.requests[0].conversation_id is None


async def test_followup_returns_exact_same_identifier(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Transmet sans altération l'identifiant d'une conversation active."""

    service = RecordingConversationService()
    await install_fake_service(application, service)
    first = await client.post(
        "/api/query",
        json={
            "question": "Où est disponible le produit 11 ?",
        },
    )
    conversation_id = first.json()["conversation_id"]

    second = await client.post(
        "/api/query",
        json={
            "conversation_id": conversation_id,
            "question": "Et à Toulouse ?",
        },
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id
    assert service.requests[-1].conversation_id == conversation_id
    assert service.requests[-1].question == "Et à Toulouse ?"


@pytest.mark.parametrize(
    "invalid_conversation_id",
    [
        "",
        " " * 32,
        "a" * 31,
        "a" * 65,
        "a" * 31 + "+",
        123,
        True,
    ],
)
async def test_invalid_conversation_identifier_returns_422(
    application: FastAPI,
    client: AsyncClient,
    invalid_conversation_id: object,
) -> None:
    """Refuse les identifiants vides, longs ou non URL-safe."""

    service = RecordingConversationService()
    await install_fake_service(application, service)

    response = await client.post(
        "/api/query",
        json={
            "conversation_id": invalid_conversation_id,
            "question": "Et à Toulouse ?",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "invalid_parameters"
    assert re.fullmatch(
        r"[A-Za-z0-9_-]{32,64}",
        body["conversation_id"],
    )
    assert service.requests == []


async def test_valid_identifier_survives_other_validation_error(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Associe une erreur de question à la conversation valide reçue."""

    conversation_id = generate_conversation_id()

    response = await client.post(
        "/api/query",
        json={
            "conversation_id": conversation_id,
            "question": "   ",
        },
    )

    assert response.status_code == 422
    assert response.json()["conversation_id"] == conversation_id


async def test_expected_error_keeps_conversation_identifier(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Conserve la session lors d'une erreur métier structurée."""

    service = RecordingConversationService()
    await install_fake_service(application, service)
    conversation_id = generate_conversation_id()

    response = await client.post(
        "/api/query",
        json={
            "conversation_id": conversation_id,
            "question": "déclenche une erreur",
        },
    )

    assert response.status_code == 503
    assert response.json()["conversation_id"] == conversation_id
    assert response.json()["error"]["code"] == "service_unavailable"


async def test_query_request_rejects_unknown_public_fields() -> None:
    """Conserve le contrat strict après ajout de conversation_id."""

    with pytest.raises(ValidationError):
        QueryRequest(
            conversation_id=generate_conversation_id(),
            question="Question valide",
            raw_mcp_response={
                "secret": True,
            },
        )
