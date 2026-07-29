"""Fixtures isolées des tests du service IA."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def application() -> FastAPI:
    """Crée une application neuve pour chaque test."""

    return create_app()


@pytest_asyncio.fixture
async def client(
    application: FastAPI,
) -> AsyncIterator[AsyncClient]:
    """Appelle FastAPI en mémoire, sans ouvrir de socket réseau."""

    transport = ASGITransport(app=application)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client
