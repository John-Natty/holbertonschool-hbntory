"""Point d'entrée FastAPI du service IA HBntory."""

import httpx
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.clients.mcp_client import ProductMCPClient
from app.config import Settings, get_settings
from app.lifespan import (
    MCPClientFactory,
    OllamaHTTPClientFactory,
    create_lifespan,
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

    del request, error

    response = ErrorResponse(
        answer=_INVALID_REQUEST_MESSAGE,
        error=ErrorDetail(
            code="invalid_parameters",
            message=_INVALID_REQUEST_MESSAGE,
        ),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=response.model_dump(mode="json"),
    )


def create_app(
    settings: Settings | None = None,
    mcp_client_factory: MCPClientFactory = ProductMCPClient,
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
            ollama_http_client_factory,
        ),
    )
    application.include_router(router)
    application.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,
    )

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
