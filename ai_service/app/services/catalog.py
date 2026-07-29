"""Instantané du catalogue Produit partagé avec le classifieur."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.data import ProductListData


logger = logging.getLogger(__name__)

# Taille de page maximale acceptée par le serveur MCP.
_PAGE_SIZE = 100

# Garde-fou contre une pagination anormale.
_MAX_PAGES = 5

# Le catalogue de l'école ne bouge pas en cours de session : un
# rafraîchissement toutes les cinq minutes suffit largement.
_TTL_SECONDS = 300.0

ProductPageFetcher = Callable[..., Awaitable["ProductListData"]]
Clock = Callable[[], float]


class CatalogSnapshot:
    """Retient les couples identifiant / nom du catalogue Produit."""

    def __init__(
        self,
        fetch_page: ProductPageFetcher,
        *,
        page_size: int = _PAGE_SIZE,
        max_pages: int = _MAX_PAGES,
        ttl_seconds: float = _TTL_SECONDS,
        clock: Clock = time.monotonic,
    ) -> None:
        """Injecte la source des pages et la politique de fraîcheur."""

        self._fetch_page = fetch_page
        self._page_size = page_size
        self._max_pages = max_pages
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: list[dict[str, object]] = []
        self._fetched_at: float | None = None
        # Deux questions simultanées ne doivent déclencher qu'un seul
        # rafraîchissement.
        self._lock = asyncio.Lock()

    async def entries(self) -> list[dict[str, object]]:
        """Retourne le catalogue, rafraîchi au plus une fois par TTL."""

        if not self._is_stale():
            return list(self._entries)

        async with self._lock:
            # Une autre tâche a pu rafraîchir pendant l'attente du verrou.
            if not self._is_stale():
                return list(self._entries)

            try:
                self._entries = await self._collect()
                self._fetched_at = self._clock()

            except Exception as error:
                # Le catalogue est un confort, jamais une dépendance dure :
                # une panne laisse le classifieur travailler sans lui.
                # Le motif est journalisé, sans quoi la panne est muette.
                logger.warning(
                    "Le catalogue n'a pas pu être rafraîchi : %s",
                    error,
                )

        return list(self._entries)

    def _is_stale(self) -> bool:
        """Indique qu'aucun instantané récent n'est disponible."""

        if self._fetched_at is None:
            return True

        return self._clock() - self._fetched_at >= self._ttl_seconds

    async def _collect(self) -> list[dict[str, object]]:
        """Parcourt les pages du catalogue et n'en garde que l'essentiel."""

        entries: list[dict[str, object]] = []
        offset = 0

        for _ in range(self._max_pages):
            page = await self._fetch_page(
                limit=self._page_size,
                offset=offset,
            )

            products = getattr(page, "products", [])

            if not products:
                break

            for product in products:
                product_id = getattr(product, "id", None)
                name = getattr(product, "name", None)

                if isinstance(product_id, int) and isinstance(name, str):
                    entries.append({"id": product_id, "nom": name})

            # La dernière page est plus courte que la taille demandée.
            if len(products) < self._page_size:
                break

            offset += self._page_size

        return entries
