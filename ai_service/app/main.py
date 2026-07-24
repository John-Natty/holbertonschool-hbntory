"""Point d'entrée FastAPI du service IA HBntory."""

import uvicorn
from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings


def create_app() -> FastAPI:
    """Crée une application FastAPI sans connexion externe."""

    application = FastAPI(
        title="HBntory AI Service",
        version="0.1.0",
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
