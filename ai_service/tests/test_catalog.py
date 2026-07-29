"""Tests de l'instantané de catalogue fourni au classifieur."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence

import pytest

from app.models.conversation import ConversationState
from app.models.data import ProductData, ProductListData
from app.models.intents import ProductDetailsIntent
from app.services.catalog import CatalogSnapshot
from app.services.context_resolver import ContextResolver
from app.services.intent_classifier import IntentClassifier


pytestmark = pytest.mark.asyncio


def _product(product_id: int, name: str) -> ProductData:
    """Construit un produit minimal accepté par le contrat MCP."""

    return ProductData(
        id=product_id,
        sku=f"SKU-{product_id}",
        name=name,
        description="Produit de test.",
        category="Tests",
        brand="Marque",
        supplier_id="SUP-1",
        supplier_name="Fournisseur",
        unit_price=19.99,
        currency="EUR",
        discontinued=False,
        weight_kg=1.0,
        tags=[],
        updated_at="2026-05-22T12:00:00Z",
    )


class RecordingPageFetcher:
    """Sert des pages contrôlées et compte chaque appel réel."""

    def __init__(
        self,
        pages: list[list[ProductData]],
        failure: BaseException | None = None,
    ) -> None:
        self.pages = pages
        self.failure = failure
        self.calls: list[tuple[int, int]] = []

    async def __call__(
        self,
        *,
        limit: int,
        offset: int,
    ) -> ProductListData:
        self.calls.append((limit, offset))

        if self.failure is not None:
            raise self.failure

        index = offset // limit if limit else 0
        products = self.pages[index] if index < len(self.pages) else []

        return ProductListData(
            count=sum(len(page) for page in self.pages),
            limit=limit,
            offset=offset,
            products=products,
        )


class FrozenClock:
    """Horloge manuelle pour piloter l'expiration sans attendre."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class RecordingCompletionClient:
    """Retourne une sortie contrôlée et conserve le prompt exact."""

    def __init__(self, outcome: str) -> None:
        self.outcome = outcome
        self.calls: list[Sequence[dict[str, str]]] = []

    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        max_tokens: int,
    ) -> str:
        self.calls.append(messages)
        return self.outcome


class BrokenCatalog:
    """Instantané qui échoue systématiquement."""

    async def entries(self) -> list[dict[str, object]]:
        raise RuntimeError("catalogue indisponible")


async def test_catalogue_retourne_les_couples_identifiant_nom() -> None:
    """Ne conserve que ce dont le classifieur a besoin."""

    fetcher = RecordingPageFetcher([[_product(4, "Écran 24 pouces")]])
    snapshot = CatalogSnapshot(fetcher, page_size=100)

    assert await snapshot.entries() == [
        {"id": 4, "nom": "Écran 24 pouces"},
    ]


async def test_catalogue_n_interroge_mcp_qu_une_fois() -> None:
    """Le cache évite un appel réseau à chaque question posée."""

    fetcher = RecordingPageFetcher([[_product(4, "Écran")]])
    snapshot = CatalogSnapshot(fetcher, page_size=100)

    await snapshot.entries()
    await snapshot.entries()
    await snapshot.entries()

    assert len(fetcher.calls) == 1


async def test_catalogue_se_rafraichit_apres_expiration() -> None:
    """Un instantané périmé est reconstruit au prochain besoin."""

    fetcher = RecordingPageFetcher([[_product(4, "Écran")]])
    clock = FrozenClock()
    snapshot = CatalogSnapshot(
        fetcher,
        page_size=100,
        ttl_seconds=300.0,
        clock=clock,
    )

    await snapshot.entries()
    clock.value = 299.0
    await snapshot.entries()

    assert len(fetcher.calls) == 1

    clock.value = 301.0
    await snapshot.entries()

    assert len(fetcher.calls) == 2


async def test_catalogue_parcourt_toutes_les_pages() -> None:
    """Un catalogue plus long qu'une page est lu entièrement."""

    fetcher = RecordingPageFetcher(
        [
            [_product(1, "A"), _product(2, "B")],
            [_product(3, "C")],
        ]
    )
    snapshot = CatalogSnapshot(fetcher, page_size=2)

    entries = await snapshot.entries()

    assert [entry["id"] for entry in entries] == [1, 2, 3]
    assert fetcher.calls == [(2, 0), (2, 2)]


async def test_panne_mcp_laisse_un_catalogue_vide() -> None:
    """Une panne ne remonte jamais jusqu'à la question de l'utilisateur."""

    fetcher = RecordingPageFetcher([], failure=RuntimeError("MCP absent"))
    snapshot = CatalogSnapshot(fetcher, page_size=100)

    assert await snapshot.entries() == []


async def test_panne_mcp_conserve_le_dernier_instantane() -> None:
    """Une coupure passagère ne fait pas perdre le catalogue connu."""

    fetcher = RecordingPageFetcher([[_product(4, "Écran")]])
    clock = FrozenClock()
    snapshot = CatalogSnapshot(
        fetcher,
        page_size=100,
        ttl_seconds=10.0,
        clock=clock,
    )

    await snapshot.entries()
    fetcher.failure = RuntimeError("MCP tombé")
    clock.value = 11.0

    assert await snapshot.entries() == [
        {"id": 4, "nom": "Écran"},
    ]


async def test_appels_simultanes_ne_declenchent_qu_un_seul_appel() -> None:
    """Deux questions en parallèle ne doublent pas la charge MCP."""

    fetcher = RecordingPageFetcher([[_product(4, "Écran")]])
    snapshot = CatalogSnapshot(fetcher, page_size=100)

    await asyncio.gather(
        snapshot.entries(),
        snapshot.entries(),
        snapshot.entries(),
    )

    assert len(fetcher.calls) == 1


async def test_un_nom_de_produit_se_resout_sans_le_modele() -> None:
    """« chaise ergonomique » désigne « Ergonomic Lab Chair », sans réseau."""

    client = RecordingCompletionClient(
        '{"intent":"unsupported","reason":"out_of_domain"}'
    )
    fetcher = RecordingPageFetcher(
        [[_product(22, "Ergonomic Lab Chair")]]
    )
    classifier = IntentClassifier(
        model_client=client,
        context_resolver=ContextResolver(),
        catalog=CatalogSnapshot(fetcher, page_size=100),
    )

    intent = await classifier.resolve(
        "parle moi de la chaise ergonomique",
        ConversationState(),
    )

    assert intent == ProductDetailsIntent(product_id=22)
    # La réponse ne doit rien au modèle : elle est immédiate et sûre.
    assert client.calls == []


async def test_un_nom_partage_par_deux_produits_ne_tranche_pas() -> None:
    """Deux écrans portent « monitor » : le raccourci doit s'abstenir."""

    client = RecordingCompletionClient(
        '{"intent":"unsupported","reason":"ambiguous"}'
    )
    fetcher = RecordingPageFetcher(
        [
            [
                _product(3, "27 inch Lab Monitor"),
                _product(4, "24 inch Compact Monitor"),
            ]
        ]
    )
    classifier = IntentClassifier(
        model_client=client,
        context_resolver=ContextResolver(),
        catalog=CatalogSnapshot(fetcher, page_size=100),
    )

    await classifier.resolve(
        "ou est le monitor ?",
        ConversationState(),
    )

    # Le modèle est consulté plutôt que de choisir un écran au hasard.
    assert len(client.calls) == 1


async def test_le_catalogue_est_transmis_au_modele() -> None:
    """Le modèle reçoit les noms quand le raccourci ne tranche pas."""

    client = RecordingCompletionClient('{"intent":"product_list"}')
    fetcher = RecordingPageFetcher(
        [[_product(22, "Ergonomic Lab Chair")]]
    )
    classifier = IntentClassifier(
        model_client=client,
        context_resolver=ContextResolver(),
        catalog=CatalogSnapshot(fetcher, page_size=100),
    )

    await classifier.resolve(
        "montre moi le catalogue",
        ConversationState(),
    )

    prompt = json.loads(client.calls[0][1]["content"])

    assert prompt["catalogue_produits"] == [
        {"id": 22, "nom": "Ergonomic Lab Chair"},
    ]


async def test_sans_catalogue_le_prompt_reste_inchange() -> None:
    """Sans instantané, le comportement est celui d'avant."""

    client = RecordingCompletionClient(
        '{"intent":"product_details","product_id":22}'
    )
    classifier = IntentClassifier(
        model_client=client,
        context_resolver=ContextResolver(),
    )

    await classifier.resolve(
        "details du produit 22",
        ConversationState(),
    )

    prompt = json.loads(client.calls[0][1]["content"])

    assert "catalogue_produits" not in prompt


async def test_catalogue_en_panne_ne_bloque_pas_la_classification() -> None:
    """Une erreur d'instantané laisse le classifieur travailler."""

    client = RecordingCompletionClient(
        '{"intent":"product_details","product_id":22}'
    )
    classifier = IntentClassifier(
        model_client=client,
        context_resolver=ContextResolver(),
        catalog=BrokenCatalog(),
    )

    intent = await classifier.resolve(
        "details du produit 22",
        ConversationState(),
    )

    prompt = json.loads(client.calls[0][1]["content"])

    assert intent == ProductDetailsIntent(product_id=22)
    assert "catalogue_produits" not in prompt
