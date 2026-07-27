"""Routage déterministe des questions françaises explicites."""

import re
import unicodedata
from typing import Protocol

from pydantic import ValidationError

from app.models.intents import (
    ProductDetailsIntent,
    ProductListIntent,
    QueryIntent,
    ShoppingListIntent,
    StockByBranchIntent,
    StockByProductIntent,
    UnsupportedIntent,
)
from app.models.mcp import ShoppingListItem


_UNSUPPORTED_REASON = (
    "La demande doit contenir une seule action et les identifiants "
    "numériques nécessaires."
)
_INVALID_SHOPPING_LIST_REASON = (
    "La liste d'achats doit contenir au moins un identifiant et une "
    "quantité strictement positive."
)

_LIST_PATTERNS = (
    re.compile(
        r"(?:liste|affiche|montre moi) (?:les|des) produits"
    ),
    re.compile(r"quels sont les produits"),
    re.compile(
        r"(?:liste|affiche|montre moi) les "
        r"(?P<limit>-?\d+) premiers produits"
    ),
    re.compile(
        r"(?:liste|affiche|montre moi) (?:les|des) produits "
        r"a partir de (?P<offset>-?\d+)"
    ),
)

_PRODUCT_DETAILS_PATTERN = re.compile(
    r"(?:details du produit|montre(?: moi)? le produit|"
    r"informations sur le produit|quel est le prix du produit) "
    r"(?P<product_id>-?\d+)"
)

_STOCK_BY_PRODUCT_PATTERN = re.compile(
    r"(?:ou trouver le produit|"
    r"dans quelles branches est disponible le produit|"
    r"stock du produit|combien reste t il du produit) "
    r"(?P<product_id>-?\d+)"
)

_STOCK_BY_BRANCH_PATTERN = re.compile(
    r"(?:stock de la branche|produits de la branche|"
    r"que contient la branche|liste le stock de la branche) "
    r"(?P<branch_id>-?\d+)"
)

_SHOPPING_LIST_PREFIXES = (
    re.compile(r"liste d achats\s*:\s*(?P<body>.*)"),
    re.compile(r"verifie la liste\s*:\s*(?P<body>.*)"),
    re.compile(r"ou acheter\s+(?P<body>.*)"),
)

_SHOPPING_LIST_ITEM_PATTERN = re.compile(
    r"(?:produit\s+)?"
    r"(?P<product_id>-?\d+)\s*x\s*"
    r"(?P<quantity>-?\d+)"
)

_SHOPPING_LIST_BODY_PATTERN = re.compile(
    r"<item>(?:\s*(?:,|et)\s*<item>)*"
)


class IntentRouter(Protocol):
    """Contrat d'un routeur d'intention asynchrone."""

    async def resolve(
        self,
        question: str,
    ) -> QueryIntent:
        """Transforme une question en intention stricte."""

        ...


class RuleBasedIntentRouter:
    """Reconnaît uniquement un ensemble documenté de formulations."""

    async def resolve(
        self,
        question: str,
    ) -> QueryIntent:
        """Retourne une intention stricte sans jamais deviner."""

        normalized = _normalize_question(question)

        shopping_intent = self._resolve_shopping_list(normalized)

        if shopping_intent is not None:
            return shopping_intent

        list_intent = self._resolve_product_list(normalized)

        if list_intent is not None:
            return list_intent

        product_details_match = _PRODUCT_DETAILS_PATTERN.fullmatch(
            normalized
        )

        if product_details_match is not None:
            return self._product_details_intent(
                product_details_match.group("product_id")
            )

        stock_by_product_match = _STOCK_BY_PRODUCT_PATTERN.fullmatch(
            normalized
        )

        if stock_by_product_match is not None:
            return self._stock_by_product_intent(
                stock_by_product_match.group("product_id")
            )

        stock_by_branch_match = _STOCK_BY_BRANCH_PATTERN.fullmatch(
            normalized
        )

        if stock_by_branch_match is not None:
            return self._stock_by_branch_intent(
                stock_by_branch_match.group("branch_id")
            )

        return UnsupportedIntent(reason=_UNSUPPORTED_REASON)

    @staticmethod
    def _resolve_product_list(
        normalized: str,
    ) -> ProductListIntent | UnsupportedIntent | None:
        """Extrait uniquement une pagination explicitement formulée."""

        for pattern in _LIST_PATTERNS:
            match = pattern.fullmatch(normalized)

            if match is None:
                continue

            values = {
                key: int(value)
                for key, value in match.groupdict().items()
                if value is not None
            }

            try:
                return ProductListIntent(**values)
            except ValidationError:
                return UnsupportedIntent(reason=_UNSUPPORTED_REASON)

        return None

    @staticmethod
    def _resolve_shopping_list(
        normalized: str,
    ) -> ShoppingListIntent | UnsupportedIntent | None:
        """Extrait les couples identifiant-quantité d'un format fermé."""

        for prefix in _SHOPPING_LIST_PREFIXES:
            prefix_match = prefix.fullmatch(normalized)

            if prefix_match is None:
                continue

            body = prefix_match.group("body").strip()
            item_matches = list(
                _SHOPPING_LIST_ITEM_PATTERN.finditer(body)
            )
            replaced_body = _SHOPPING_LIST_ITEM_PATTERN.sub(
                "<item>",
                body,
            )

            if (
                not item_matches
                or _SHOPPING_LIST_BODY_PATTERN.fullmatch(
                    replaced_body
                )
                is None
            ):
                return UnsupportedIntent(
                    reason=_INVALID_SHOPPING_LIST_REASON
                )

            try:
                items = [
                    ShoppingListItem(
                        product_id=int(
                            match.group("product_id")
                        ),
                        quantity=int(match.group("quantity")),
                    )
                    for match in item_matches
                ]

                return ShoppingListIntent(items=items)
            except ValidationError:
                return UnsupportedIntent(
                    reason=_INVALID_SHOPPING_LIST_REASON
                )

        return None

    @staticmethod
    def _product_details_intent(
        product_id: str,
    ) -> ProductDetailsIntent | UnsupportedIntent:
        """Valide l'identifiant d'une demande de détail."""

        try:
            return ProductDetailsIntent(
                product_id=int(product_id)
            )
        except ValidationError:
            return UnsupportedIntent(reason=_UNSUPPORTED_REASON)

    @staticmethod
    def _stock_by_product_intent(
        product_id: str,
    ) -> StockByProductIntent | UnsupportedIntent:
        """Valide l'identifiant d'une demande de stock Produit."""

        try:
            return StockByProductIntent(
                product_id=int(product_id)
            )
        except ValidationError:
            return UnsupportedIntent(reason=_UNSUPPORTED_REASON)

    @staticmethod
    def _stock_by_branch_intent(
        branch_id: str,
    ) -> StockByBranchIntent | UnsupportedIntent:
        """Valide l'identifiant d'une demande de stock Branche."""

        try:
            return StockByBranchIntent(
                branch_id=int(branch_id)
            )
        except ValidationError:
            return UnsupportedIntent(reason=_UNSUPPORTED_REASON)


def _normalize_question(question: str) -> str:
    """Normalise casse, accents et ponctuation sans changer les nombres."""

    decomposed = unicodedata.normalize(
        "NFKD",
        question,
    )
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    normalized = without_accents.lower()
    normalized = re.sub(
        r"(?<=[a-z])[-‐‑–—](?=[a-z])",
        " ",
        normalized,
    )
    normalized = re.sub(
        r"['’ʼ]",
        " ",
        normalized,
    )
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip(" ?!.")
