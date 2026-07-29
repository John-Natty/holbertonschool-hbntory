"""Tests ASGI des routes publiques du service IA."""

import re

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.dependencies import get_query_orchestrator
from app.models.conversation import generate_conversation_id
from app.models.query import (
    QueryRequest,
    QueryResponse,
    UnsupportedResponse,
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


def without_conversation_id(body: dict) -> dict:
    """Valide puis retire l'identifiant opaque d'une assertion statique."""

    conversation_id = body.pop("conversation_id")
    assert re.fullmatch(
        r"[A-Za-z0-9_-]{32,64}",
        conversation_id,
    )
    return body


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

        return UnsupportedResponse(
            conversation_id=(
                request.conversation_id
                or generate_conversation_id()
            ),
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
        "/api/query",
        json={
            "question": "Où trouver le produit 12 ?",
        },
    )

    assert response.status_code == 503
    assert without_conversation_id(response.json()) == {
        "success": False,
        "answer": (
            "Le service de données est temporairement indisponible."
        ),
        "type": "error",
        "data": None,
        "error": {
            "code": "service_unavailable",
            "message": "Le serveur MCP n’est pas connecté.",
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
        "/api/query",
        json=payload,
    )

    assert response.status_code == 422
    assert without_conversation_id(
        response.json()
    ) == INVALID_REQUEST_RESPONSE
    assert set(response.json()) == {
        "conversation_id",
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
        "/api/query",
        content='{"question":',
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422
    assert without_conversation_id(
        response.json()
    ) == INVALID_REQUEST_RESPONSE


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
        get_query_orchestrator
    ] = get_fake_service

    response = await client.post(
        "/api/query",
        json={
            "question": "  Question valide  ",
        },
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "conversation_id",
        "success",
        "answer",
        "type",
        "data",
        "error",
    }
    conversation_id = response.json()["conversation_id"]
    assert re.fullmatch(
        r"[A-Za-z0-9_-]{32,64}",
        conversation_id,
    )
    assert response.json() == {
        "conversation_id": conversation_id,
        "success": True,
        "answer": "La question a été validée.",
        "type": "unsupported",
        "data": None,
        "error": None,
    }
    assert fake_service.request is not None
    assert fake_service.request.question == "Question valide"


async def test_openapi_exposes_all_public_routes(
    application: FastAPI,
):
    """Documente le catalogue sans modifier les routes existantes."""

    paths = application.openapi()["paths"]

    assert "get" in paths["/health"]
    assert "get" in paths["/ready"]
    assert "get" in paths["/api/products"]
    assert "post" in paths["/api/query"]
    assert "/query" not in paths
    assert paths["/api/query"]["post"]["responses"]["422"] == {
        "description": "Unprocessable Entity",
        "content": {
            "application/json": {
                "schema": {
                    "$ref": "#/components/schemas/ErrorResponse",
                }
            }
        },
    }
    assert paths["/api/products"]["get"]["responses"]["422"] == {
        "description": "Unprocessable Entity",
        "content": {
            "application/json": {
                    "schema": {
                        "$ref": (
                            "#/components/schemas/"
                            "ProductCatalogErrorResponse"
                        ),
                }
            }
        },
    }


async def test_legacy_query_route_returns_404(
    client: AsyncClient,
) -> None:
    """N'expose plus l'ancien chemin public sans préfixe."""

    response = await client.post(
        "/query",
        json={
            "question": "Où trouver le produit 12 ?",
        },
    )

    assert response.status_code == 404
