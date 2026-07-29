"""Tests ASGI de POST /api/query relié à l'orchestrateur MCP."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.errors import (
    MCPConnectionError,
    MCPInvalidArgumentError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPToolResponseError,
)
from app.models.data import (
    BranchData,
    ProductData,
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
)
from app.models.mcp import ShoppingListItem
from app.main import create_app


pytestmark = pytest.mark.asyncio

OUT_OF_DOMAIN_ANSWER = (
    "Je peux uniquement répondre aux questions concernant les produits, "
    "les stocks, les branches et les listes d’achats de HBntory."
)
READ_ONLY_ANSWER = (
    "Cette demande n’est pas disponible : HBntory permet uniquement de "
    "consulter les produits, les stocks, les branches et les listes d’achats."
)


def without_conversation_id(body: dict) -> dict:
    """Valide puis retire l'identifiant opaque d'une assertion statique."""

    conversation_id = body.pop("conversation_id")
    assert re.fullmatch(
        r"[A-Za-z0-9_-]{32,64}",
        conversation_id,
    )
    return body


def product_data() -> ProductData:
    """Construit le produit validé renvoyé par le faux client."""

    return ProductData(
        id=12,
        sku="HB-TEST-0012",
        name="Produit de test",
        description="Description.",
        category="Tests",
        brand="HBntory",
        supplier_id="SUP-001",
        supplier_name="Fournisseur",
        unit_price=19.99,
        currency="EUR",
        discontinued=False,
        weight_kg=1.25,
        tags=["test"],
        updated_at="2026-07-24T12:00:00Z",
        supplier=None,
    )


class FakeApplicationMCPClient:
    """Faux client complet injecté dans le lifespan FastAPI."""

    def __init__(
        self,
        *,
        connect_error: Exception | None = None,
        method_error: Exception | None = None,
    ) -> None:
        """Prépare le cycle de vie et les résultats MCP validés."""

        self._ready = False
        self.connect_error = connect_error
        self.method_error = method_error
        self.connect_count = 0
        self.ensure_count = 0
        self.close_count = 0
        self.calls: list[tuple[str, object]] = []
        self.products = ProductListData(
            count=1,
            limit=10,
            offset=5,
            products=[product_data()],
        )
        self.details = ProductDetailsData(
            product=product_data()
        )
        self.by_product = StockByProductData(
            product_id=12,
            branches=[
                {
                    "branch_id": 1,
                    "branch_name": "Toulouse",
                    "quantity": 8,
                }
            ],
        )
        self.by_branch = StockByBranchData(
            branch=BranchData(
                id=3,
                name="Carcassonne",
            ),
            stocks=[
                {
                    "product_id": 12,
                    "product_name": "Produit de test",
                    "unit_price": 49.99,
                    "currency": "EUR",
                    "quantity": 8,
                }
            ],
        )
        self.shopping = ShoppingListData(
            matching_branches=[
                {
                    "branch_id": 1,
                    "branch_name": "Toulouse",
                    "items": [
                        {
                            "product_id": 12,
                            "requested_quantity": 2,
                            "available_quantity": 8,
                        },
                        {
                            "product_id": 7,
                            "requested_quantity": 1,
                            "available_quantity": 4,
                        },
                    ],
                }
            ]
        )

    @property
    def is_ready(self) -> bool:
        """Expose l'état de la fausse connexion."""

        return self._ready

    async def ensure_connected(self) -> bool:
        """Simule une restauration de session avant une requête."""

        self.ensure_count += 1

        if self._ready:
            return True

        try:
            await self.connect()
        except MCPConnectionError:
            return False

        return self._ready

    async def connect(self) -> None:
        """Simule l'initialisation du client partagé."""

        self.connect_count += 1

        if self.connect_error is not None:
            raise self.connect_error

        self._ready = True

    async def close(self) -> None:
        """Simule la fermeture du client partagé."""

        self.close_count += 1
        self._ready = False

    def _raise_method_error(self) -> None:
        """Lève l'erreur configurée à la place des données."""

        if self.method_error is not None:
            raise self.method_error

    async def list_products(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> ProductListData:
        """Retourne une page dont la pagination suit la demande."""

        self.calls.append(
            (
                "list_products",
                {
                    "limit": limit,
                    "offset": offset,
                },
            )
        )
        self._raise_method_error()
        self.products = ProductListData(
            count=self.products.count,
            limit=limit,
            offset=offset,
            products=self.products.products,
        )
        return self.products

    async def get_product_details(
        self,
        product_id: int,
    ) -> ProductDetailsData:
        """Retourne le détail Produit configuré."""

        self.calls.append(
            (
                "get_product_details",
                {
                    "product_id": product_id,
                },
            )
        )
        self._raise_method_error()
        return self.details

    async def get_stock_by_product(
        self,
        product_id: int,
    ) -> StockByProductData:
        """Retourne le stock Produit configuré."""

        self.calls.append(
            (
                "get_stock_by_product",
                {
                    "product_id": product_id,
                },
            )
        )
        self._raise_method_error()
        return self.by_product

    async def get_stock_by_branch(
        self,
        branch_id: int,
    ) -> StockByBranchData:
        """Retourne le stock Branche configuré."""

        self.calls.append(
            (
                "get_stock_by_branch",
                {
                    "branch_id": branch_id,
                },
            )
        )
        self._raise_method_error()
        return self.by_branch

    async def check_shopping_list(
        self,
        items: list[ShoppingListItem],
    ) -> ShoppingListData:
        """Retourne les branches satisfaisant la liste."""

        self.calls.append(
            (
                "check_shopping_list",
                {
                    "items": [
                        item.model_dump()
                        for item in items
                    ],
                },
            )
        )
        self._raise_method_error()
        return self.shopping


def create_test_settings() -> Settings:
    """Retourne la configuration locale utilisée par les tests ASGI."""

    return Settings(
        mcp_server_url="http://mcp.test/mcp",
        mcp_request_timeout_seconds=1,
        mcp_max_concurrent_calls=2,
        ai_model_provider="rules",
    )


@asynccontextmanager
async def application_client(
    mcp_client: FakeApplicationMCPClient,
) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    """Démarre le lifespan avec un faux client sans réseau."""

    def client_factory(
        **_configuration: object,
    ) -> FakeApplicationMCPClient:
        return mcp_client

    application = create_app(
        settings=create_test_settings(),
        mcp_client_factory=client_factory,
    )
    transport = ASGITransport(app=application)

    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield application, client


@pytest.mark.parametrize(
    (
        "question",
        "expected_type",
        "expected_call",
        "data_attribute",
        "expected_answer",
    ),
    [
        (
            "liste les 10 premiers produits",
            "product_list",
            (
                "list_products",
                {
                    "limit": 10,
                    "offset": 0,
                },
            ),
            "products",
            (
                "1 produit a été trouvé :\n\n"
                "- #12 — Produit de test — 19,99 EUR"
            ),
        ),
        (
            "détails du produit 12",
            "product_details",
            (
                "get_product_details",
                {
                    "product_id": 12,
                },
            ),
            "details",
            (
                "Le produit 12 est « Produit de test » et coûte "
                "19,99 EUR."
            ),
        ),
        (
            "où trouver le produit 12",
            "stock_by_product",
            (
                "get_stock_by_product",
                {
                    "product_id": 12,
                },
            ),
            "by_product",
            (
                "Le produit 12 est disponible dans la branche "
                "Toulouse, avec 8 unités en stock."
            ),
        ),
        (
            "stock de la branche 3",
            "stock_by_branch",
            (
                "get_stock_by_branch",
                {
                    "branch_id": 3,
                },
            ),
            "by_branch",
            (
                "La branche Carcassonne possède 1 référence en stock :\n"
                "- Produit n°12 — Quantité : 8 — "
                "Nom : Produit de test — Prix unitaire : 49,99 EUR"
            ),
        ),
        (
            "vérifie la liste : 12 x2, 7 x1",
            "shopping_list",
            (
                "check_shopping_list",
                {
                    "items": [
                        {
                            "product_id": 12,
                            "quantity": 2,
                        },
                        {
                            "product_id": 7,
                            "quantity": 1,
                        },
                    ],
                },
            ),
            "shopping",
            (
                "La branche Toulouse peut satisfaire entièrement cette "
                "liste d’achats."
            ),
        ),
    ],
)
async def test_query_routes_each_intent_to_one_mcp_method(
    question: str,
    expected_type: str,
    expected_call: tuple[str, object],
    data_attribute: str,
    expected_answer: str,
) -> None:
    """Retourne un contrat exact pour chacune des cinq intentions."""

    mcp_client = FakeApplicationMCPClient()

    async with application_client(mcp_client) as (
        _application,
        client,
    ):
        response = await client.post(
            "/api/query",
            json={
                "question": question,
            },
        )

    assert response.status_code == 200
    assert without_conversation_id(response.json()) == {
        "success": True,
        "answer": expected_answer,
        "type": expected_type,
        "data": getattr(
            mcp_client,
            data_attribute,
        ).model_dump(mode="json"),
        "error": None,
    }
    assert mcp_client.calls == [expected_call]
    assert mcp_client.connect_count == 1
    assert mcp_client.close_count == 1


@pytest.mark.parametrize(
    ("question", "expected_answer"),
    [
        (
            "quelle est la météo ?",
            OUT_OF_DOMAIN_ANSWER,
        ),
        (
            "raconte-moi une blague",
            OUT_OF_DOMAIN_ANSWER,
        ),
        (
            "qui est le président ?",
            OUT_OF_DOMAIN_ANSWER,
        ),
        (
            "donne-moi une recette",
            OUT_OF_DOMAIN_ANSWER,
        ),
        (
            "combien font deux plus deux ?",
            OUT_OF_DOMAIN_ANSWER,
        ),
        (
            "écris-moi du JavaScript",
            OUT_OF_DOMAIN_ANSWER,
        ),
        (
            "donne-moi les détails du produit",
            "Veuillez préciser l’identifiant du produit.",
        ),
        (
            "où est disponible cet article ?",
            "Veuillez préciser l’identifiant du produit.",
        ),
            (
                "montre-moi le stock de la branche",
                (
                    "Veuillez préciser le nom ou l’identifiant "
                    "de la branche."
                ),
            ),
        (
            "vérifie ma liste d’achats",
            (
                "Veuillez préciser les produits et les quantités de votre "
                "liste."
            ),
        ),
        (
            "ajoute 10 unités du produit 4",
            READ_ONLY_ANSWER,
        ),
        (
            "supprime le produit 8",
            READ_ONLY_ANSWER,
        ),
        (
            "modifie le stock de la branche 2",
            READ_ONLY_ANSWER,
        ),
        (
            "crée une nouvelle agence",
            READ_ONLY_ANSWER,
        ),
    ],
)
async def test_query_returns_unsupported_without_mcp_call(
    question: str,
    expected_answer: str,
) -> None:
    """Refuse ou clarifie avant toute connexion ou lecture MCP."""

    mcp_client = FakeApplicationMCPClient()

    async with application_client(mcp_client) as (
        _application,
        client,
    ):
        response = await client.post(
            "/api/query",
            json={
                "question": question,
            },
        )

    assert response.status_code == 200
    assert without_conversation_id(response.json()) == {
        "success": True,
        "answer": expected_answer,
        "type": "unsupported",
        "data": None,
        "error": None,
    }
    assert mcp_client.calls == []
    assert mcp_client.ensure_count == 0


async def test_query_returns_503_when_mcp_connection_failed() -> None:
    """Conserve l'API disponible avec une erreur REST exacte."""

    mcp_client = FakeApplicationMCPClient(
        connect_error=MCPConnectionError(
            "adresse interne sensible"
        )
    )

    async with application_client(mcp_client) as (
        _application,
        client,
    ):
        response = await client.post(
            "/api/query",
            json={
                "question": "détails du produit 12",
            },
        )

    assert response.status_code == 503
    assert without_conversation_id(response.json()) == {
        "success": False,
        "answer": (
            "Le service de données est temporairement indisponible."
        ),
        "type": "error",
        "data": None,
        "error": {
            "code": "service_unavailable",
            "message": "Le serveur MCP n’est pas connecté.",
        },
    }
    assert "adresse interne sensible" not in response.text
    assert mcp_client.calls == []


async def test_query_reconnects_before_single_business_call() -> None:
    """Récupère la session puis exécute exactement un outil MCP."""

    mcp_client = FakeApplicationMCPClient(
        connect_error=MCPConnectionError(
            "Connexion initiale indisponible."
        )
    )

    async with application_client(mcp_client) as (
        _application,
        client,
    ):
        mcp_client.connect_error = None
        response = await client.post(
            "/api/query",
            json={
                "question": "détails du produit 12",
            },
        )

    assert response.status_code == 200
    assert response.json()["type"] == "product_details"
    assert mcp_client.connect_count == 2
    assert mcp_client.ensure_count == 1
    assert mcp_client.calls == [
        (
            "get_product_details",
            {
                "product_id": 12,
            },
        )
    ]


async def test_catalog_route_and_user_query_keep_independent_limits() -> None:
    """Sépare la pagination technique de la question utilisateur."""

    mcp_client = FakeApplicationMCPClient()

    async with application_client(mcp_client) as (
        _application,
        client,
    ):
        catalog_response = await client.get(
            "/api/products?limit=100&offset=0"
        )
        query_response = await client.post(
            "/api/query",
            json={
                "question": "liste les 10 premiers produits",
            },
        )

    assert catalog_response.status_code == 200
    assert catalog_response.json()["data"]["limit"] == 100
    assert query_response.status_code == 200
    assert query_response.json()["data"]["limit"] == 10
    assert mcp_client.calls == [
        (
            "list_products",
            {
                "limit": 100,
                "offset": 0,
            },
        ),
        (
            "list_products",
            {
                "limit": 10,
                "offset": 0,
            },
        ),
    ]


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            MCPTimeoutError("contenu technique"),
            504,
            "service_timeout",
        ),
        (
            MCPProtocolError("contenu technique"),
            502,
            "invalid_service_response",
        ),
        (
            MCPToolResponseError(
                "get_product_details",
                "resource_not_found",
            ),
            404,
            "resource_not_found",
        ),
        (
            MCPToolResponseError(
                "get_product_details",
                "client_error",
            ),
            502,
            "client_error",
        ),
        (
            MCPInvalidArgumentError("contenu technique"),
            422,
            "invalid_parameters",
        ),
    ],
)
async def test_query_maps_expected_errors_to_http(
    error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    """Associe chaque erreur contrôlée à son statut HTTP."""

    mcp_client = FakeApplicationMCPClient(
        method_error=error
    )

    async with application_client(mcp_client) as (
        _application,
        client,
    ):
        response = await client.post(
            "/api/query",
            json={
                "question": "détails du produit 12",
            },
        )

    assert response.status_code == expected_status
    body = response.json()
    assert set(body) == {
        "conversation_id",
        "success",
        "answer",
        "type",
        "data",
        "error",
    }
    assert body["success"] is False
    assert body["type"] == "error"
    assert body["data"] is None
    assert body["error"]["code"] == expected_code
    assert "contenu technique" not in response.text
    assert len(mcp_client.calls) == 1


async def test_unknown_product_returns_clear_public_response() -> None:
    """Explique clairement qu'un produit demandé est introuvable."""

    mcp_client = FakeApplicationMCPClient(
        method_error=MCPToolResponseError(
            "get_product_details",
            "product_not_found",
        )
    )

    async with application_client(mcp_client) as (
        _application,
        client,
    ):
        response = await client.post(
            "/api/query",
            json={
                "question": "détails du produit 999999",
            },
        )

    assert response.status_code == 404
    assert without_conversation_id(response.json()) == {
        "success": False,
        "answer": "La ressource demandée n’a pas été trouvée.",
        "type": "error",
        "data": None,
        "error": {
            "code": "resource_not_found",
            "message": (
                "Le produit ou la branche demandé n’existe pas."
            ),
        },
    }
    assert mcp_client.calls == [
        (
            "get_product_details",
            {
                "product_id": 999999,
            },
        )
    ]


async def test_query_returns_generic_500_for_unexpected_bug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Masque le détail public sans le convertir dans l'orchestrateur."""

    mcp_client = FakeApplicationMCPClient(
        method_error=RuntimeError("détail interne sensible")
    )

    async with application_client(mcp_client) as (
        _application,
        client,
    ):
        response = await client.post(
            "/api/query",
            json={
                "question": "détails du produit 12",
            },
        )

    assert response.status_code == 500
    assert without_conversation_id(response.json()) == {
        "success": False,
        "answer": (
            "Une erreur interne empêche le traitement de la demande."
        ),
        "type": "error",
        "data": None,
        "error": {
            "code": "internal_error",
            "message": (
                "Le service IA a rencontré une erreur inattendue."
            ),
        },
    }
    assert "détail interne sensible" not in response.text
    assert "détail interne sensible" not in caplog.text
