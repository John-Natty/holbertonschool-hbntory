"""Résolution déterministe des seules références conversationnelles sûres."""

from __future__ import annotations

import re
import unicodedata

from app.models.conversation import ConversationState
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


_NUMBER_WORDS = {
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "treize": 13,
    "quatorze": 14,
    "quinze": 15,
    "seize": 16,
    "vingt": 20,
}
_NUMBER = r"(?:\d+|" + "|".join(_NUMBER_WORDS) + r")"
_ORDINAL_VALUES = {
    "premier": 0,
    "premiere": 0,
    "deuxieme": 1,
    "troisieme": 2,
    "quatrieme": 3,
    "cinquieme": 4,
    "sixieme": 5,
    "septieme": 6,
    "huitieme": 7,
    "neuvieme": 8,
    "dixieme": 9,
    "onzieme": 10,
    "douzieme": 11,
    "treizieme": 12,
    "quatorzieme": 13,
    "quinzieme": 14,
    "seizieme": 15,
    "vingtieme": 19,
}
_ORDINAL_PATTERN = re.compile(
    r"\b(?:le|la)?\s*(?P<ordinal>"
    + "|".join(_ORDINAL_VALUES)
    + r"|dernier|derniere)\b"
)
_PRODUCT_FOLLOWUP_PATTERN = re.compile(
    r"\bet\s+(?:pour\s+)?(?:le\s+)?"
    r"(?:produit|article|reference)\s+(?P<product_id>\d+)\b"
)
_EXPLICIT_PRODUCT_PATTERN = re.compile(
    r"\b(?:produits?|articles?|references?)\s+"
    rf"(?:numero\s+)?(?P<product_id>{_NUMBER})\b"
)
_SHOPPING_UPDATE_PATTERN = re.compile(
    rf"\b(?P<quantity>{_NUMBER})\s+"
    r"(?:unites?\s+)?(?:du|de|pour)?\s*"
    r"(?:produits?|articles?|references?)\s+"
    r"(?P<product_id>\d+)\b"
)
_SHOPPING_PRODUCT_FIRST_PATTERN = re.compile(
    rf"\b(?:(?:produit|article|reference)\s+)?"
    rf"(?P<product_id>\d+)"
    rf"\s*(?:x|fois|quantite)\s*(?P<quantity>{_NUMBER})\b"
)
_LIST_LIMIT_PATTERN = re.compile(
    rf"\b(?P<limit>{_NUMBER})\s+"
    r"(?:premiers?\s+)?(?:produits?|articles?)\b"
)
_LIST_OFFSET_PATTERN = re.compile(
    rf"\ba partir (?:de|du)\s+(?P<offset>{_NUMBER})\b"
)
_BRANCH_FOLLOWUP_PATTERN = re.compile(
    r"^(?:et\s+)?(?:a|dans|pour)\s+"
    r"(?:(?:la|l)\s+)?(?:(?:branche|agence)\s+(?:de\s+)?)?"
    r"(?P<branch>[a-z][a-z0-9' -]{0,99})$"
)
_BRANCH_ID_PATTERN = re.compile(
    r"\b(?:branche|agence)\s+(?:numero\s+)?(?P<branch_id>\d+)\b"
)
_BRANCH_NAME_PATTERN = re.compile(
    r"\b(?:a|dans)\s+"
    r"(?:(?:la|l)\s+)?(?:(?:branche|agence)\s+(?:de\s+)?)"
    r"(?P<branch>[a-z][a-z0-9' -]{0,99})$"
)
_AVAILABILITY_AT_PATTERN = re.compile(
    r"\b(?:disponibles?|stock|reste)\s+(?:a|dans)\s+"
    r"(?:(?:la|l)\s+)?(?:(?:branche|agence)\s+(?:de\s+)?)?"
    r"(?P<branch>[a-z][a-z0-9' -]{0,99})$"
)
_STOCK_OF_BRANCH_NAME_PATTERN = re.compile(
    r"\b(?:stock|inventaire|produits?)\s+(?:de|du)\s+"
    r"(?:(?:la|l)\s+)?(?:(?:branche|agence)\s+(?:de\s+)?)?"
    r"(?P<branch>[a-z][a-z0-9' -]{0,99})$"
)

_OUT_OF_DOMAIN_TERMS = (
    "meteo",
    "politique",
    "president",
    "recette",
    "programmation",
    "code python",
    "javascript",
    "blague",
)
_PROMPT_INJECTION_TERMS = (
    "ignore les instructions",
    "ignore toutes les instructions",
    "ignore previous instructions",
    "oublie les instructions",
    "system prompt",
)
_WRITE_PATTERN = re.compile(
    r"^(?:et\s+)?(?:peux tu\s+|merci de\s+|je veux que tu\s+)?"
    r"(?:ajoute|ajouter|retire|supprime|supprimer|cree|creer|"
    r"modifie|modifier|augmente|dimininue|diminue)\b"
)
_STOCK_MARKERS = (
    "disponible",
    "disponibilite",
    "stock",
    "reste",
    "trouver",
    "branche",
    "agence",
)
_DETAIL_MARKERS = (
    "detail",
    "information",
    "parle",
    "prix",
    "description",
)
_PRONOUN_MARKERS = (
    "celui ci",
    "ce produit",
    "cette reference",
    "le trouver",
    "en reste",
)
_SAME_BRANCH_MARKERS = (
    "cette branche",
    "cette agence",
    "au meme endroit",
    "dans le meme endroit",
)
_INVALID_BRANCH_NAMES = {
    "branche",
    "agence",
    "quelle branche",
    "quelles branches",
    "quelle agence",
    "quelles agences",
}


class ContextResolver:
    """Résout un suivi si, et seulement si, l'état le justifie."""

    def resolve(
        self,
        question: str,
        state: ConversationState,
        proposed: QueryIntent | None = None,
    ) -> QueryIntent | None:
        """Protège, résout les références puis revalide une proposition."""

        normalized = _normalize(question)
        guarded = self._guard(normalized)

        if guarded is not None:
            return guarded

        contextual = self._resolve_contextual(normalized, state)

        if contextual is not None:
            return contextual

        if proposed is None:
            return None

        return self._validate_proposed(normalized, state, proposed)

    def _guard(self, normalized: str) -> UnsupportedIntent | None:
        """Refuse le hors domaine et les écritures avant toute mémoire."""

        if any(
            marker in normalized
            for marker in _PROMPT_INJECTION_TERMS
        ):
            return _unsupported("out_of_domain")

        if any(term in normalized for term in _OUT_OF_DOMAIN_TERMS):
            return _unsupported("out_of_domain")

        if _WRITE_PATTERN.search(normalized):
            return _unsupported("read_only")

        return None

    def _resolve_contextual(
        self,
        normalized: str,
        state: ConversationState,
    ) -> QueryIntent | None:
        """Traite un petit ensemble de références explicites et bornées."""

        # Une question qui nomme elle-même son produit se suffit à elle
        # même : ce n'est pas une reprise du tour précédent, et les
        # résolutions par référence ne doivent pas la confisquer.
        explicit_product = (
            _EXPLICIT_PRODUCT_PATTERN.search(normalized) is not None
        )

        ordinal_match = _ORDINAL_PATTERN.search(normalized)

        if ordinal_match is not None:
            return self._resolve_ordinal(
                ordinal_match.group("ordinal"),
                state,
            )

        if state.shopping_items and (
            "j en veux" in normalized
            or "quantite" in normalized
            or normalized.startswith("et si")
        ):
            updates = list(
                _SHOPPING_UPDATE_PATTERN.finditer(normalized)
            )

            if updates:
                return self._update_shopping_list(updates, state)

        product_match = _PRODUCT_FOLLOWUP_PATTERN.search(normalized)

        if product_match is not None:
            return self._switch_product(
                int(product_match.group("product_id")),
                state,
            )

        if any(marker in normalized for marker in _SAME_BRANCH_MARKERS):
            return self._reuse_branch(normalized, state)

        # « Et à Toulouse ? » change la branche du tour précédent. Une
        # question qui cite son propre produit n'entre pas dans ce cas,
        # même lorsqu'elle commence par « dans ».
        branch_match = (
            None
            if explicit_product
            else _BRANCH_FOLLOWUP_PATTERN.fullmatch(normalized)
        )

        if branch_match is not None:
            branch_name = _clean_branch_name(
                branch_match.group("branch")
            )
            return self._switch_branch(branch_name, state)

        if not explicit_product and (
            "ou puis je le trouver" in normalized
            or ("combien" in normalized and "reste" in normalized)
        ):
            if state.last_product_id is None:
                return _unsupported("missing_product_id")

            return StockByProductIntent(
                product_id=state.last_product_id,
                **_state_branch_reference(state),
            )

        if not explicit_product and any(
            marker in normalized for marker in _PRONOUN_MARKERS
        ):
            return self._resolve_product_pronoun(normalized, state)

        combined = self._resolve_combined_product_branch(normalized)

        if combined is not None:
            return combined

        branch_id, branch_name = _extract_branch(normalized)

        if (
            (branch_id is not None or branch_name is not None)
            and any(marker in normalized for marker in _STOCK_MARKERS)
        ):
            return StockByBranchIntent(
                branch_id=branch_id,
                branch_name=branch_name,
            )

        return None

    def _resolve_ordinal(
        self,
        ordinal: str,
        state: ConversationState,
    ) -> QueryIntent:
        """Mappe une position uniquement sur la dernière liste réelle."""

        if not state.last_product_ids:
            return _unsupported("ambiguous")

        if ordinal in {"dernier", "derniere"}:
            index = len(state.last_product_ids) - 1
        else:
            index = _ORDINAL_VALUES[ordinal]

        if index >= len(state.last_product_ids):
            return _unsupported("ambiguous")

        return ProductDetailsIntent(
            product_id=state.last_product_ids[index]
        )

    def _switch_branch(
        self,
        branch_name: str,
        state: ConversationState,
    ) -> QueryIntent:
        """Conserve le produit ou le type de stock du tour précédent."""

        if (
            state.last_intent == "stock_by_product"
            and state.last_product_id is not None
        ):
            return StockByProductIntent(
                product_id=state.last_product_id,
                branch_name=branch_name,
            )

        if state.last_intent == "stock_by_branch":
            return StockByBranchIntent(branch_name=branch_name)

        if state.last_product_id is not None:
            return StockByProductIntent(
                product_id=state.last_product_id,
                branch_name=branch_name,
            )

        return _unsupported("ambiguous")

    def _switch_product(
        self,
        product_id: int,
        state: ConversationState,
    ) -> QueryIntent:
        """Conserve l'opération précédente sans inventer une quantité."""

        if state.last_intent == "stock_by_product":
            return StockByProductIntent(
                product_id=product_id,
                **_state_branch_reference(state),
            )

        if state.last_intent == "stock_by_branch":
            return StockByProductIntent(
                product_id=product_id,
                **_state_branch_reference(state),
            )

        if state.last_intent == "shopping_list":
            return _unsupported("missing_items")

        if state.last_intent is None:
            return _unsupported("ambiguous")

        return ProductDetailsIntent(product_id=product_id)

    def _reuse_branch(
        self,
        normalized: str,
        state: ConversationState,
    ) -> QueryIntent:
        """Réutilise seulement une branche réellement mémorisée."""

        if (
            state.last_branch_id is None
            and state.last_branch_name is None
        ):
            return _unsupported("missing_branch_id")

        product_match = _EXPLICIT_PRODUCT_PATTERN.search(normalized)
        product_id = (
            int(product_match.group("product_id"))
            if product_match is not None
            else state.last_product_id
        )

        if product_id is not None and (
            any(marker in normalized for marker in _STOCK_MARKERS)
            or state.last_intent == "stock_by_product"
        ):
            return StockByProductIntent(
                product_id=product_id,
                **_state_branch_reference(state),
            )

        return StockByBranchIntent(
            **_state_branch_reference(state),
        )

    def _resolve_product_pronoun(
        self,
        normalized: str,
        state: ConversationState,
    ) -> QueryIntent:
        """Réutilise le dernier produit seulement s'il existe."""

        if state.last_product_id is None:
            return _unsupported("missing_product_id")

        if any(marker in normalized for marker in _STOCK_MARKERS):
            return StockByProductIntent(
                product_id=state.last_product_id,
                **_state_branch_reference(state),
            )

        if any(marker in normalized for marker in _DETAIL_MARKERS):
            return ProductDetailsIntent(
                product_id=state.last_product_id
            )

        if state.last_intent == "stock_by_product":
            return StockByProductIntent(
                product_id=state.last_product_id,
                **_state_branch_reference(state),
            )

        if state.last_intent == "product_details":
            return ProductDetailsIntent(
                product_id=state.last_product_id
            )

        return _unsupported("ambiguous")

    def _resolve_combined_product_branch(
        self,
        normalized: str,
    ) -> StockByProductIntent | None:
        """Conserve les deux contraintes avec un seul futur appel MCP."""

        if not any(marker in normalized for marker in _STOCK_MARKERS):
            return None

        product_match = _EXPLICIT_PRODUCT_PATTERN.search(normalized)

        if product_match is None:
            return None

        branch_id, branch_name = _extract_branch(normalized)

        if branch_id is None and branch_name is None:
            return None

        return StockByProductIntent(
            product_id=int(product_match.group("product_id")),
            branch_id=branch_id,
            branch_name=branch_name,
        )

    def _update_shopping_list(
        self,
        updates: list[re.Match[str]],
        state: ConversationState,
    ) -> ShoppingListIntent:
        """Met à jour les quantités et normalise chaque produit une fois."""

        quantities = {
            item.product_id: item.quantity
            for item in state.shopping_items
        }

        for match in updates:
            quantities[int(match.group("product_id"))] = _parse_number(
                match.group("quantity")
            )

        return ShoppingListIntent(
            items=[
                ShoppingListItem(
                    product_id=product_id,
                    quantity=quantity,
                )
                for product_id, quantity in quantities.items()
            ]
        )

    def _validate_proposed(
        self,
        normalized: str,
        state: ConversationState,
        proposed: QueryIntent,
    ) -> QueryIntent:
        """Enrichit sans autoriser une référence conversationnelle fictive."""

        if isinstance(proposed, StockByProductIntent):
            anchored_product_id = _extract_product_id(normalized)

            if (
                anchored_product_id is not None
                and anchored_product_id != proposed.product_id
            ):
                return _unsupported("ambiguous")

            if (
                anchored_product_id is None
                and _has_context_product_reference(normalized)
                and state.last_product_id != proposed.product_id
            ):
                return _unsupported("ambiguous")

            if (
                anchored_product_id is None
                and not _has_context_product_reference(normalized)
            ):
                return _unsupported("ambiguous")

            branch_id, branch_name = _extract_branch(normalized)

            if (
                proposed.branch_id is None
                and proposed.branch_name is None
                and (branch_id is not None or branch_name is not None)
            ):
                return StockByProductIntent(
                    product_id=proposed.product_id,
                    branch_id=branch_id,
                    branch_name=branch_name,
                )

            if proposed.branch_name is not None:
                clean_name = _clean_branch_name(
                    proposed.branch_name
                )

                if not _branch_name_is_anchored(
                    clean_name,
                    normalized,
                    state,
                ):
                    return _unsupported("ambiguous")

                return StockByProductIntent(
                    product_id=proposed.product_id,
                    branch_name=clean_name,
                )

            if (
                proposed.branch_id is not None
                and not _branch_id_is_anchored(
                    proposed.branch_id,
                    normalized,
                    state,
                )
            ):
                return _unsupported("ambiguous")

        if (
            isinstance(proposed, StockByBranchIntent)
            and proposed.branch_name is not None
        ):
            clean_name = _clean_branch_name(proposed.branch_name)

            if not _branch_name_is_anchored(
                clean_name,
                normalized,
                state,
            ):
                return _unsupported("ambiguous")

            return StockByBranchIntent(
                branch_name=clean_name,
            )

        if (
            isinstance(proposed, StockByBranchIntent)
            and proposed.branch_id is not None
            and not _branch_id_is_anchored(
                proposed.branch_id,
                normalized,
                state,
            )
        ):
            return _unsupported("ambiguous")

        if isinstance(proposed, ProductDetailsIntent):
            anchored_product_id = _extract_product_id(normalized)

            if (
                anchored_product_id is not None
                and anchored_product_id != proposed.product_id
            ):
                return _unsupported("ambiguous")

            if (
                anchored_product_id is None
                and _has_context_product_reference(normalized)
                and state.last_product_id != proposed.product_id
            ):
                return _unsupported("ambiguous")

            if (
                anchored_product_id is None
                and not _has_context_product_reference(normalized)
            ):
                return _unsupported("ambiguous")

        if isinstance(proposed, ProductListIntent):
            limit_match = _LIST_LIMIT_PATTERN.search(normalized)
            offset_match = _LIST_OFFSET_PATTERN.search(normalized)
            anchored_limit = (
                _parse_number(limit_match.group("limit"))
                if limit_match is not None
                else 20
            )
            anchored_offset = (
                _parse_number(offset_match.group("offset"))
                if offset_match is not None
                else 0
            )

            if (
                proposed.limit != anchored_limit
                or proposed.offset != anchored_offset
            ):
                return _unsupported("ambiguous")

        if isinstance(proposed, ShoppingListIntent):
            anchored_items = _extract_shopping_items(normalized)

            if anchored_items is None:
                return _unsupported("missing_items")

            proposed_items = {
                item.product_id: item.quantity
                for item in proposed.items
            }

            if proposed_items != anchored_items:
                return _unsupported("ambiguous")

        return proposed


def _extract_branch(
    normalized: str,
) -> tuple[int | None, str | None]:
    """Extrait une branche explicite sans deviner un nom libre."""

    id_match = _BRANCH_ID_PATTERN.search(normalized)

    if id_match is not None:
        return int(id_match.group("branch_id")), None

    for pattern in (
        _BRANCH_NAME_PATTERN,
        _AVAILABILITY_AT_PATTERN,
        _STOCK_OF_BRANCH_NAME_PATTERN,
    ):
        name_match = pattern.search(normalized)

        if name_match is not None:
            branch_name = _clean_branch_name(
                name_match.group("branch")
            )

            if (
                branch_name.casefold() not in _INVALID_BRANCH_NAMES
                and not _looks_like_product_reference(branch_name)
            ):
                return None, branch_name

    return None, None


def _clean_branch_name(value: str) -> str:
    """Retire seulement les prépositions parasites connues."""

    normalized = " ".join(value.strip(" ?!.").split())
    normalized = re.sub(r"^(?:de|du)\s+", "", normalized)
    return normalized.title()


def _looks_like_product_reference(value: str) -> bool:
    """Empêche « stock du produit 11 » de devenir un nom de branche."""

    normalized = _normalize(value)
    return re.fullmatch(
        rf"(?:produits?|articles?|references?|materiels?)\s+{_NUMBER}",
        normalized,
    ) is not None


def _extract_product_id(normalized: str) -> int | None:
    """Retourne l'identifiant produit explicitement écrit, s'il existe."""

    match = _EXPLICIT_PRODUCT_PATTERN.search(normalized)
    return (
        _parse_number(match.group("product_id"))
        if match is not None
        else None
    )


def _extract_shopping_items(
    normalized: str,
) -> dict[int, int] | None:
    """Extrait et normalise les couples explicites d'une liste."""

    positioned: list[tuple[int, int, int]] = []

    for pattern in (
        _SHOPPING_UPDATE_PATTERN,
        _SHOPPING_PRODUCT_FIRST_PATTERN,
    ):
        for match in pattern.finditer(normalized):
            positioned.append(
                (
                    match.start(),
                    int(match.group("product_id")),
                    _parse_number(match.group("quantity")),
                )
            )

    if not positioned:
        return None

    positioned.sort()
    quantities: dict[int, int] = {}
    seen: set[tuple[int, int, int]] = set()

    for item in positioned:
        if item in seen:
            continue

        seen.add(item)
        _, product_id, quantity = item
        quantities[product_id] = (
            quantities.get(product_id, 0) + quantity
        )

    return quantities


def _state_branch_reference(
    state: ConversationState,
) -> dict[str, int | str]:
    """Choisit une seule référence de branche, l'identifiant en priorité."""

    if state.last_branch_id is not None:
        return {"branch_id": state.last_branch_id}

    if state.last_branch_name is not None:
        return {"branch_name": state.last_branch_name}

    return {}


def _has_context_product_reference(normalized: str) -> bool:
    """Détecte une référence qui doit provenir de la mémoire."""

    return (
        _ORDINAL_PATTERN.search(normalized) is not None
        or any(marker in normalized for marker in _PRONOUN_MARKERS)
    )


def _branch_name_is_anchored(
    branch_name: str,
    normalized: str,
    state: ConversationState,
) -> bool:
    """Vérifie un nom contre la question ou la branche mémorisée."""

    normalized_name = _normalize(branch_name)

    if normalized_name and normalized_name in normalized:
        return True

    if any(marker in normalized for marker in _SAME_BRANCH_MARKERS):
        return (
            state.last_branch_name is not None
            and _normalize(state.last_branch_name) == normalized_name
        )

    return False


def _branch_id_is_anchored(
    branch_id: int,
    normalized: str,
    state: ConversationState,
) -> bool:
    """Vérifie un identifiant de branche contre l'entrée ou la mémoire."""

    match = _BRANCH_ID_PATTERN.search(normalized)

    if match is not None:
        return int(match.group("branch_id")) == branch_id

    if any(marker in normalized for marker in _SAME_BRANCH_MARKERS):
        return state.last_branch_id == branch_id

    return False


def _parse_number(value: str) -> int:
    """Convertit un entier ou un petit nombre français borné."""

    if value.isdigit():
        return int(value)

    return _NUMBER_WORDS[value]


def _normalize(value: str) -> str:
    """Normalise accents, apostrophes et ponctuation sans donnée externe."""

    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    normalized = re.sub(
        r"[^a-z0-9' ]+",
        " ",
        without_accents.replace("’", " "),
    )
    return " ".join(normalized.replace("'", " ").split())


def _unsupported(reason_code: str) -> UnsupportedIntent:
    """Construit une clarification publique sans détail technique."""

    messages = {
        "out_of_domain": (
            "La question ne concerne pas le domaine HBntory."
        ),
        "read_only": "La demande tente une écriture interdite.",
        "missing_product_id": (
            "Aucun produit de la conversation ne correspond à la référence."
        ),
        "missing_branch_id": (
            "Aucune branche de la conversation ne correspond à la référence."
        ),
        "missing_items": (
            "La quantité nécessaire à la liste d’achats est absente."
        ),
        "ambiguous": (
            "La référence ne correspond à aucun résultat récent."
        ),
    }
    return UnsupportedIntent(
        reason_code=reason_code,
        reason=messages[reason_code],
    )
