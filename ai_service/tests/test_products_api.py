"""Tests ASGI de la route technique GET /api/products."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.dependencies import get_mcp_client
from app.errors import MCPProtocolError
from app.models.data import ProductData, ProductListData
from app.services.answer_builder import AnswerBuilder


pytestmark = pytest.mark.asyncio


def product_data(product_id: int = 4) -> ProductData:
    """Construit un produit complet déjà validé."""

    return ProductData(
        id=product_id,
        sku=f"HB-TEST-{product_id:04d}",
        name=f"Produit {product_id}",
        description="Description validée.",
        category="Tests",
        brand="HBntory",
        supplier_id="SUP-001",
        supplier_name="Fournisseur",
        unit_price=169.99,
        currency="USD",
        discontinued=False,
        weight_kg=1.25,
        tags=["test"],
        updated_at="2026-07-24T12:00:00Z",
        supplier=None,
    )


class FakeCatalogMCPClient:
    """Simule uniquement la reconnexion et list_products."""

    def __init__(
        self,
        products: list[ProductData] | None = None,
    ) -> None:
        """Prépare une page adaptable à la pagination reçue."""

        resolved_products = (
            products
            if products is not None
            else [product_data()]
        )
        self.page = ProductListData(
            count=len(resolved_products),
            limit=100,
            offset=0,
            products=resolved_products,
        )
        self.ensure_result = True
        self.ensure_count = 0
        self.calls: list[tuple[str, dict[str, int]]] = []
        self.error: Exception | None = None
        self.adapt_pagination = True

    async def ensure_connected(self) -> bool:
        """Retourne l'état de connexion configuré."""

        self.ensure_count += 1
        return self.ensure_result

    async def list_products(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> ProductListData:
        """Enregistre l'unique appel métier attendu."""

        self.calls.append(
            (
                "list_products",
                {
                    "limit": limit,
                    "offset": offset,
                },
            )
        )

        if self.error is not None:
            raise self.error

        if not self.adapt_pagination:
            return self.page

        return ProductListData(
            count=self.page.count,
            limit=limit,
            offset=offset,
            products=self.page.products[:limit],
        )


async def override_catalog_client(
    application: FastAPI,
    fake_client: FakeCatalogMCPClient,
) -> None:
    """Injecte le client MCP partagé simulé."""

    async def dependency() -> FakeCatalogMCPClient:
        return fake_client

    application.dependency_overrides[get_mcp_client] = dependency


async def test_products_returns_structured_page_with_one_mcp_call(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Retourne les données exactes via le seul outil list_products."""

    fake_client = FakeCatalogMCPClient(
        [product_data(index) for index in range(1, 11)]
    )
    await override_catalog_client(application, fake_client)

    response = await client.get(
        "/api/products",
        params={
            "limit": 10,
            "offset": 20,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["error"] is None
    assert payload["data"]["limit"] == 10
    assert payload["data"]["offset"] == 20
    assert payload["data"]["count"] == 10
    assert len(payload["data"]["products"]) == 10
    assert payload["data"]["products"][0]["id"] == 1
    assert payload["data"]["products"][0]["unit_price"] == 169.99
    assert fake_client.ensure_count == 1
    assert fake_client.calls == [
        (
            "list_products",
            {
                "limit": 10,
                "offset": 20,
            },
        )
    ]


async def test_products_uses_default_limit_of_one_hundred(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Charge jusqu'à cent produits lorsque la pagination est absente."""

    fake_client = FakeCatalogMCPClient()
    await override_catalog_client(application, fake_client)

    response = await client.get("/api/products")

    assert response.status_code == 200
    assert response.json()["data"]["limit"] == 100
    assert response.json()["data"]["offset"] == 0
    assert fake_client.calls == [
        (
            "list_products",
            {
                "limit": 100,
                "offset": 0,
            },
        )
    ]


async def test_products_empty_page_remains_successful(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Conserve HTTP 200 pour un catalogue vide."""

    fake_client = FakeCatalogMCPClient([])
    await override_catalog_client(application, fake_client)

    response = await client.get("/api/products")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "count": 0,
            "limit": 100,
            "offset": 0,
            "products": [],
        },
        "error": None,
    }
    assert len(fake_client.calls) == 1


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=-1",
        "limit=101",
        "offset=-1",
        "limit=test",
    ],
)
async def test_products_rejects_invalid_parameters_before_mcp(
    query: str,
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Refuse la pagination invalide sans connexion ni appel métier."""

    fake_client = FakeCatalogMCPClient()
    await override_catalog_client(application, fake_client)

    response = await client.get(f"/api/products?{query}")

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "invalid_parameters"
    assert fake_client.ensure_count == 0
    assert fake_client.calls == []


async def test_products_returns_structured_503_when_mcp_is_unavailable(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Signale l'indisponibilité sans tenter list_products."""

    fake_client = FakeCatalogMCPClient()
    fake_client.ensure_result = False
    await override_catalog_client(application, fake_client)

    response = await client.get("/api/products")

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {
            "code": "service_unavailable",
            "message": "Le catalogue est temporairement indisponible.",
        },
    }
    assert fake_client.ensure_count == 1
    assert fake_client.calls == []


async def test_products_rejects_invalid_mcp_response(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Convertit une réponse MCP invalide en erreur structurée."""

    fake_client = FakeCatalogMCPClient()
    fake_client.error = MCPProtocolError("Détail interne.")
    await override_catalog_client(application, fake_client)

    response = await client.get("/api/products")

    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "invalid_service_response",
        "message": (
            "Le service de catalogue a retourné une réponse invalide."
        ),
    }
    assert "Détail interne" not in response.text
    assert len(fake_client.calls) == 1


async def test_products_rejects_incoherent_mcp_pagination(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Refuse une page dont limite et offset ne suivent pas la demande."""

    fake_client = FakeCatalogMCPClient()
    fake_client.adapt_pagination = False
    await override_catalog_client(application, fake_client)

    response = await client.get(
        "/api/products?limit=10&offset=20"
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == (
        "invalid_service_response"
    )
    assert len(fake_client.calls) == 1


class ForbiddenSemanticComponent:
    """Échoue si la route technique tente une classification."""

    def __init__(self) -> None:
        """Prépare le compteur d'appels interdits."""

        self.calls = 0

    async def resolve(self, _question: str) -> None:
        """Interdit tout appel du routeur."""

        self.calls += 1
        raise AssertionError("Le routeur ne doit pas être appelé.")

    async def classify(self, _question: str) -> None:
        """Interdit tout appel Ollama."""

        self.calls += 1
        raise AssertionError("Ollama ne doit pas être appelé.")


async def test_products_bypasses_all_semantic_components(
    application: FastAPI,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contourne routeur, Ollama et AnswerBuilder."""

    fake_client = FakeCatalogMCPClient()
    await override_catalog_client(application, fake_client)
    router = ForbiddenSemanticComponent()
    classifier = ForbiddenSemanticComponent()
    application.state.intent_classifier = router
    application.state.intent_classifier = classifier

    def forbidden_builder(
        _builder: AnswerBuilder,
        _data: ProductListData,
    ) -> None:
        raise AssertionError("AnswerBuilder ne doit pas être appelé.")

    monkeypatch.setattr(
        AnswerBuilder,
        "product_list",
        forbidden_builder,
    )

    response = await client.get("/api/products")

    assert response.status_code == 200
    assert router.calls == 0
    assert classifier.calls == 0
    assert len(fake_client.calls) == 1


async def test_products_does_not_change_other_public_routes(
    application: FastAPI,
    client: AsyncClient,
) -> None:
    """Laisse la santé et la route de question accessibles."""

    fake_client = FakeCatalogMCPClient()
    await override_catalog_client(application, fake_client)

    health_response = await client.get("/health")
    query_response = await client.post(
        "/api/query",
        json={"question": "liste les produits"},
    )

    assert health_response.status_code == 200
    assert query_response.status_code == 503
    assert fake_client.calls == []
