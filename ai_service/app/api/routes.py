"""Routes publiques du service IA HBntory."""

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import (
    get_mcp_client,
    get_query_service,
)
from app.clients.mcp_client import ProductMCPClient
from app.models.health import (
    HealthResponse,
    NotReadyResponse,
    ReadyResponse,
)
from app.models.query import (
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.query_service import QueryService


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def health() -> HealthResponse:
    """Confirme que le processus du service IA fonctionne."""

    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadyResponse | NotReadyResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": NotReadyResponse,
        },
    },
)
async def ready(
    response: Response,
    client: ProductMCPClient | None = Depends(get_mcp_client),
) -> ReadyResponse | NotReadyResponse:
    """Expose l'état courant du client sans tenter de reconnexion."""

    if client is not None and client.is_ready:
        return ReadyResponse()

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return NotReadyResponse()


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
        },
    },
)
async def query(
    request: QueryRequest,
    response: Response,
    service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    """Valide une question et la transmet au service injecté."""

    result = await service.handle(request)

    if isinstance(result, ErrorResponse):
        response.status_code = _error_status_code(result)

    return result


def _error_status_code(result: ErrorResponse) -> int:
    """Associe une erreur métier à un statut HTTP public."""

    status_codes = {
        "invalid_parameters": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "resource_not_found": status.HTTP_404_NOT_FOUND,
        "service_timeout": status.HTTP_504_GATEWAY_TIMEOUT,
        "service_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "invalid_service_response": status.HTTP_502_BAD_GATEWAY,
        "client_error": status.HTTP_502_BAD_GATEWAY,
        "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }

    return status_codes[result.error.code]
