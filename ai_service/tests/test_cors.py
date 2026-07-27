"""Tests ASGI de la politique CORS du service IA."""

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio

ALLOWED_ORIGIN = "http://localhost:8080"
FORBIDDEN_ORIGIN = "https://attacker.example"


async def test_allowed_preflight_exposes_expected_policy(
    client: AsyncClient,
) -> None:
    """Autorise le client web pour POST avec un contenu JSON."""

    response = await client.options(
        "/api/query",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == ALLOWED_ORIGIN
    )
    allowed_methods = {
        method.strip()
        for method in response.headers[
            "access-control-allow-methods"
        ].split(",")
    }
    assert "POST" in allowed_methods
    assert (
        "content-type"
        in response.headers[
            "access-control-allow-headers"
        ].lower()
    )
    assert "access-control-allow-credentials" not in response.headers


async def test_allowed_post_exposes_exact_origin(
    client: AsyncClient,
) -> None:
    """Ajoute l'autorisation CORS à une réponse métier."""

    response = await client.post(
        "/api/query",
        headers={
            "Origin": ALLOWED_ORIGIN,
        },
        json={
            "question": "Où trouver le produit 12 ?",
        },
    )

    assert response.status_code == 503
    assert (
        response.headers["access-control-allow-origin"]
        == ALLOWED_ORIGIN
    )
    assert "access-control-allow-credentials" not in response.headers


async def test_forbidden_origin_is_not_authorized(
    client: AsyncClient,
) -> None:
    """Ne renvoie aucune autorisation à une origine inconnue."""

    response = await client.options(
        "/api/query",
        headers={
            "Origin": FORBIDDEN_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert (
        response.headers.get("access-control-allow-origin")
        != FORBIDDEN_ORIGIN
    )
    assert "access-control-allow-credentials" not in response.headers
