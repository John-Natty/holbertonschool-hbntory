"""Dépendances injectables des routes du service IA."""

from app.services.query_service import (
    QueryService,
    UnavailableQueryService,
)


_query_service = UnavailableQueryService()


async def get_query_service() -> QueryService:
    """Retourne le service de requête utilisé par l'API."""

    return _query_service
