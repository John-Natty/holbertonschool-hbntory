"""Point d'entrée FastAPI du service IA HBntory."""

import httpx
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.clients.mcp_client import ProductMCPClient
from app.clients.minimax_client import MiniMaxClient
from app.config import Settings, get_settings
from app.lifespan import (
    MCPClientFactory,
    MiniMaxClientFactory,
    OllamaHTTPClientFactory,
    active_provider,
    create_lifespan,
    provider_status,
)
from app.models.catalog import ProductCatalogErrorResponse
from app.models.conversation import (
    generate_conversation_id,
    validate_conversation_id,
)
from app.models.query import ErrorDetail, ErrorResponse


_INVALID_REQUEST_MESSAGE = (
    "La requête contient des paramètres invalides."
)


async def request_validation_error_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    """Retourne une erreur 422 stable sans détail Pydantic public."""

    error_detail = ErrorDetail(
        code="invalid_parameters",
        message=_INVALID_REQUEST_MESSAGE,
    )

    if request.url.path == "/api/query":
        conversation_id = generate_conversation_id()
        body = getattr(error, "body", None)

        if isinstance(body, dict):
            candidate = body.get("conversation_id")

            if isinstance(candidate, str):
                try:
                    conversation_id = validate_conversation_id(
                        candidate
                    )
                except ValueError:
                    pass

        response = ErrorResponse(
            conversation_id=conversation_id,
            answer=_INVALID_REQUEST_MESSAGE,
            error=error_detail,
        )
    else:
        response = ProductCatalogErrorResponse(
            error=error_detail,
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=response.model_dump(mode="json"),
    )


def create_app(
    settings: Settings | None = None,
    mcp_client_factory: MCPClientFactory = ProductMCPClient,
    minimax_client_factory: MiniMaxClientFactory = MiniMaxClient,
    ollama_http_client_factory: OllamaHTTPClientFactory = (
        httpx.AsyncClient
    ),
) -> FastAPI:
    """Crée l'application et injecte le lifespan du client MCP."""

    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="HBntory AI Service",
        version="0.1.0",
        lifespan=create_lifespan(
            resolved_settings,
            mcp_client_factory,
            minimax_client_factory,
            ollama_http_client_factory,
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    application.include_router(router)
    application.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,
    )
    application.state.ai_model_provider = (
        resolved_settings.ai_model_provider
    )
    application.state.ai_provider_status = provider_status(
        resolved_settings
    )
    application.state.active_ai_provider = active_provider(
        resolved_settings
    )
    application.state.query_orchestrator = None

    return application


app = create_app()


def main() -> None:
    """Lance localement le serveur HTTP avec la configuration."""

    settings = get_settings()

    uvicorn.run(
        app,
        host=settings.ai_service_host,
        port=settings.ai_service_port,
    )


if __name__ == "__main__":
    main()
