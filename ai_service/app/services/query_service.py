"""Services de traitement des questions publiques."""

from typing import TYPE_CHECKING, Protocol

from app.models.query import (
    ErrorDetail,
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)

if TYPE_CHECKING:
    from app.services.orchestrator import QueryOrchestrator


class QueryService(Protocol):
    """Contrat asynchrone du traitement d'une requête."""

    async def handle(
        self,
        request: QueryRequest,
    ) -> QueryResponse:
        """Traite une question publique validée."""

        ...


class MCPQueryService:
    """Transmet une requête validée à l'orchestrateur déterministe."""

    def __init__(
        self,
        orchestrator: "QueryOrchestrator",
    ) -> None:
        """Injecte l'orchestrateur partagé du lifespan."""

        self._orchestrator = orchestrator

    async def handle(
        self,
        request: QueryRequest,
    ) -> QueryResponse:
        """Retourne la réponse construite depuis les données MCP."""

        return await self._orchestrator.handle(request.question)


class UnavailableQueryService:
    """Signale explicitement l'absence du service partagé."""

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
