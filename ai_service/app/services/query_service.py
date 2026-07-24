"""Abstraction temporaire du traitement des questions."""

from typing import Protocol

from app.models.query import (
    ErrorDetail,
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)


class QueryService(Protocol):
    """Contrat asynchrone du futur orchestrateur de requêtes."""

    async def handle(
        self,
        request: QueryRequest,
    ) -> QueryResponse:
        """Traite une question publique validée."""

        ...


class UnavailableQueryService:
    """Signale explicitement que le client MCP n'existe pas encore."""

    async def handle(
        self,
        request: QueryRequest,
    ) -> QueryResponse:
        """Retourne une indisponibilité sans inventer de donnée."""

        del request

        return ErrorResponse(
            answer=(
                "Le service de données est temporairement indisponible."
            ),
            error=ErrorDetail(
                code="service_unavailable",
                message="Le serveur MCP n’est pas encore connecté.",
            ),
        )
