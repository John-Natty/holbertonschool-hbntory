"""Tests ASGI des routes publiques du service IA."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.dependencies import get_query_service
from app.models.query import (
    QueryRequest,
    QueryResponse,
    TextResponse,
)


pytestmark = pytest.mark.asyncio

INVALID_REQUEST_RESPONSE = {
    "success": False,
    "answer": "La requête contient des paramètres invalides.",
    "type": "error",
    "data": None,
    "error": {
        "code": "invalid_parameters",
        "message": "La requête contient des paramètres invalides.",
    },
}


class SuccessfulQueryService:
    """Faux service retournant une réponse réussie sans réseau."""

    def __init__(self) -> None:
        """Prépare l'enregistrement de la requête reçue."""

        self.request = None

    async def handle(
        self,
        request: QueryRequest,
    ) -> QueryResponse:
        """Retourne une réponse textuelle déterministe."""

        self.request = request

        return TextResponse(
            answer="La question a été validée.",
        )


async def test_health_returns_service_status(
    client: AsyncClient,
):
    """Retourne la santé du processus sans dépendance externe."""

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ai-service",
    }


async def test_query_returns_structured_unavailable_error(
    client: AsyncClient,
):
    """Signale temporairement que le client MCP est absent."""

    response = await client.post(
        "/query",
        json={
            "question": "Où trouver le produit 12 ?",
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "answer": (
            "Le service de données est temporairement indisponible."
        ),
        "type": "error",
        "data": None,
        "error": {
            "code": "service_unavailable",
            "message": "Le serveur MCP n’est pas encore connecté.",
        },
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "question": "",
        },
        {
            "question": "   ",
        },
        {
            "question": "x" * 2001,
        },
        {
            "question": 12,
        },
        {
            "question": True,
        },
        {
            "question": "Question valide",
            "unexpected": True,
        },
    ],
)
async def test_query_returns_structured_422(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    """Retourne le même contrat public pour toute entrée invalide."""

    response = await client.post(
        "/query",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == INVALID_REQUEST_RESPONSE
    assert set(response.json()) == {
        "success",
        "answer",
        "type",
        "data",
        "error",
    }
    assert set(response.json()["error"]) == {
        "code",
        "message",
    }


async def test_query_returns_structured_422_for_malformed_json(
    client: AsyncClient,
) -> None:
    """Masque également les détails du parseur JSON."""

    response = await client.post(
        "/query",
        content='{"question":',
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422
    assert response.json() == INVALID_REQUEST_RESPONSE


async def test_injected_service_returns_success(
    application: FastAPI,
    client: AsyncClient,
):
    """Remplace la dépendance et retourne une réponse HTTP 200."""

    fake_service = SuccessfulQueryService()

    async def get_fake_service() -> SuccessfulQueryService:
        """Retourne le faux service sans passer par un threadpool."""

        return fake_service

    application.dependency_overrides[
        get_query_service
    ] = get_fake_service

    response = await client.post(
        "/query",
        json={
            "question": "  Question valide  ",
        },
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "success",
        "answer",
        "type",
        "data",
        "error",
    }
    assert response.json() == {
        "success": True,
        "answer": "La question a été validée.",
        "type": "text",
        "data": None,
        "error": None,
    }
    assert fake_service.request is not None
    assert fake_service.request.question == "Question valide"


async def test_openapi_exposes_health_ready_and_query(
    application: FastAPI,
):
    """Documente les trois routes prévues pour cette phase."""

    paths = application.openapi()["paths"]

    assert "get" in paths["/health"]
    assert "get" in paths["/ready"]
    assert "post" in paths["/query"]
    assert paths["/query"]["post"]["responses"]["422"] == {
        "description": "Unprocessable Entity",
        "content": {
            "application/json": {
                "schema": {
                    "$ref": "#/components/schemas/ErrorResponse",
                }
            }
        },
    }
