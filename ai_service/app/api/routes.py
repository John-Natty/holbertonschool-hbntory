"""Routes publiques du service IA HBntory."""

import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
    status,
)

from app.api.dependencies import (
    get_mcp_client,
    get_query_orchestrator,
)
from app.clients.mcp_client import ProductMCPClient
from app.errors import (
    MCPClientError,
    MCPConnectionError,
    MCPInvalidArgumentError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPToolResponseError,
)
from app.models.catalog import (
    ProductCatalogErrorResponse,
    ProductCatalogResponse,
    ProductCatalogSuccessResponse,
)
from app.models.health import (
    HealthResponse,
    NotReadyResponse,
    ReadyResponse,
)
from app.models.conversation import generate_conversation_id
from app.models.query import (
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.answer_builder import AnswerBuilder
from app.services.orchestrator import QueryOrchestrator
from app.services.product_page import validate_product_page


router = APIRouter()
logger = logging.getLogger(__name__)
_answer_builder = AnswerBuilder()
CatalogLimit = Annotated[int, Query(ge=1, le=100)]
CatalogOffset = Annotated[int, Query(ge=0)]

_CATALOG_ERROR_MESSAGES: dict[ErrorCode, str] = {
    "invalid_parameters": (
        "Les paramètres du catalogue sont invalides."
    ),
    "resource_not_found": (
        "La ressource du catalogue demandée n’existe pas."
    ),
    "service_timeout": (
        "Le chargement du catalogue a dépassé le délai autorisé."
    ),
    "service_unavailable": (
        "Le catalogue est temporairement indisponible."
    ),
    "invalid_service_response": (
        "Le service de catalogue a retourné une réponse invalide."
    ),
    "client_error": (
        "Le catalogue n’a pas pu être chargé."
    ),
    "internal_error": (
        "Une erreur interne empêche le chargement du catalogue."
    ),
}


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
    request: Request,
    response: Response,
    client: ProductMCPClient | None = Depends(get_mcp_client),
) -> ReadyResponse | NotReadyResponse:
    """Expose l'état après une vérification ou reconnexion MCP bornée."""

    provider = request.app.state.ai_model_provider
    provider_status = request.app.state.ai_provider_status
    active_provider = request.app.state.active_ai_provider

    if client is not None and await client.ensure_connected():
        return ReadyResponse(
            provider=provider,
            provider_status=provider_status,
            active_provider=active_provider,
        )

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return NotReadyResponse(
        provider=provider,
        provider_status=provider_status,
        active_provider=active_provider,
    )


@router.get(
    "/api/products",
    response_model=ProductCatalogResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ProductCatalogErrorResponse,
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ProductCatalogErrorResponse,
        },
        status.HTTP_502_BAD_GATEWAY: {
            "model": ProductCatalogErrorResponse,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ProductCatalogErrorResponse,
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "model": ProductCatalogErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ProductCatalogErrorResponse,
        },
    },
)
async def products(
    response: Response,
    limit: CatalogLimit = 100,
    offset: CatalogOffset = 0,
    client: ProductMCPClient | None = Depends(get_mcp_client),
) -> ProductCatalogResponse:
    """Charge une page Produit sans classification ni génération."""

    if client is None:
        return _catalog_error(
            response,
            "service_unavailable",
        )

    try:
        if not await client.ensure_connected():
            return _catalog_error(
                response,
                "service_unavailable",
            )

        data = await client.list_products(
            limit=limit,
            offset=offset,
        )
        validate_product_page(data, limit, offset)

        return ProductCatalogSuccessResponse(data=data)
    except MCPToolResponseError as error:
        return _catalog_error(
            response,
            _catalog_tool_error_code(error.code),
        )
    except MCPTimeoutError:
        return _catalog_error(response, "service_timeout")
    except MCPConnectionError:
        return _catalog_error(response, "service_unavailable")
    except MCPInvalidArgumentError:
        return _catalog_error(response, "invalid_parameters")
    except MCPProtocolError:
        return _catalog_error(
            response,
            "invalid_service_response",
        )
    except MCPClientError:
        return _catalog_error(response, "client_error")
    except Exception as error:
        logger.error(
            "Une erreur inattendue a interrompu GET /api/products "
            "(type=%s).",
            type(error).__name__,
        )
        return _catalog_error(response, "internal_error")


@router.post(
    "/api/query",
    response_model=QueryResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ErrorResponse,
        },
        status.HTTP_502_BAD_GATEWAY: {
            "model": ErrorResponse,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
        },
    },
)
async def query(
    request: QueryRequest,
    response: Response,
    orchestrator: QueryOrchestrator | None = Depends(
        get_query_orchestrator
    ),
) -> QueryResponse:
    """Valide une question et la transmet au service injecté."""

    conversation_id = (
        request.conversation_id or generate_conversation_id()
    )

    if orchestrator is None:
        result = _answer_builder.error(
            "service_unavailable",
            conversation_id=conversation_id,
        )
        response.status_code = _error_status_code(result)
        return result

    try:
        result = await orchestrator.handle(request)
    except Exception as error:
        logger.error(
            "Une erreur inattendue a interrompu POST /api/query "
            "(type=%s).",
            type(error).__name__,
        )
        result = _answer_builder.error(
            "internal_error",
            conversation_id=conversation_id,
        )

    if isinstance(result, ErrorResponse):
        response.status_code = _error_status_code(result)

    return result


def _error_status_code(result: ErrorResponse) -> int:
    """Associe une erreur métier à un statut HTTP public."""

    return _error_code_status(result.error.code)


def _error_code_status(code: ErrorCode) -> int:
    """Associe un code public à son statut HTTP."""

    status_codes = {
        "invalid_parameters": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "resource_not_found": status.HTTP_404_NOT_FOUND,
        "service_timeout": status.HTTP_504_GATEWAY_TIMEOUT,
        "service_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "invalid_service_response": status.HTTP_502_BAD_GATEWAY,
        "client_error": status.HTTP_502_BAD_GATEWAY,
        "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }

    return status_codes[code]


def _catalog_error(
    response: Response,
    code: ErrorCode,
) -> ProductCatalogErrorResponse:
    """Construit une erreur structurée propre au catalogue."""

    response.status_code = _error_code_status(code)

    return ProductCatalogErrorResponse(
        error=ErrorDetail(
            code=code,
            message=_CATALOG_ERROR_MESSAGES[code],
        )
    )


def _catalog_tool_error_code(code: str) -> ErrorCode:
    """Convertit un code MCP en code public du catalogue."""

    mappings: dict[str, ErrorCode] = {
        "resource_not_found": "resource_not_found",
        "invalid_parameters": "invalid_parameters",
        "service_timeout": "service_timeout",
        "service_unavailable": "service_unavailable",
        "invalid_service_response": "invalid_service_response",
        "client_error": "client_error",
    }

    return mappings.get(code, "client_error")
