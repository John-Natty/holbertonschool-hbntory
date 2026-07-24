"""Point d'entrée FastAPI du service IA HBntory."""

import uvicorn
from fastapi import FastAPI

from app.api.routes import router
from app.clients.mcp_client import ProductMCPClient
from app.config import Settings, get_settings
from app.lifespan import MCPClientFactory, create_lifespan


def create_app(
    settings: Settings | None = None,
    mcp_client_factory: MCPClientFactory = ProductMCPClient,
) -> FastAPI:
    """Crée l'application et injecte le lifespan du client MCP."""

    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="HBntory AI Service",
        version="0.1.0",
        lifespan=create_lifespan(
            resolved_settings,
            mcp_client_factory,
        ),
    )
    application.include_router(router)

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
