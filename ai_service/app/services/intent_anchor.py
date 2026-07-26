"""Validation de l'ancrage d'une intention dans la question."""

from collections import Counter
import re
import unicodedata

from app.models.intents import (
    ProductDetailsIntent,
    ProductListIntent,
    QueryIntent,
    ShoppingListIntent,
    StockByBranchIntent,
    StockByProductIntent,
    UnsupportedIntent,
)


_AUTONOMOUS_NUMBER_PATTERN = re.compile(
    r"(?<![\w+-])\d+(?!\w)"
)
_SIGNED_NUMBER_PATTERN = re.compile(
    r"(?<!\d)-?\d+(?!\d)"
)
_PRODUCT_FIRST_PAIR_PATTERN = re.compile(
    r"(?:produit\s+)?"
    r"(?P<product_id>\d+)\s*"
    r"(?:x|quantite\s*)\s*"
    r"(?P<quantity>\d+)"
)
_QUANTITY_FIRST_PAIR_PATTERN = re.compile(
    r"(?P<quantity>\d+)\s*"
    r"(?:unite|unites|exemplaire|exemplaires)\s+"
    r"(?:du\s+)?produit\s+"
    r"(?P<product_id>\d+)"
)
_LIMIT_PATTERNS = (
    re.compile(r"(?<!\w)(\d+)\s+premiers?\s+produits"),
    re.compile(
        r"(?:limite|limit|maximum|max)\s*(?:de\s*)?(\d+)"
    ),
    re.compile(r"(?<!\w)(\d+)\s+produits"),
)
_OFFSET_PATTERNS = (
    re.compile(r"a partir de\s+(\d+)"),
    re.compile(r"offset\s+(\d+)"),
    re.compile(r"apres\s+(\d+)"),
)
_INJECTION_MARKERS = (
    "ignore toutes les instructions",
    "ignore les instructions",
    "ignore previous instructions",
    "oublie les instructions",
    "system prompt",
    "product_id",
    "branch_id",
    "appelle directement",
    "list_products",
    "get_product_details",
    "get_stock_by_product",
    "get_stock_by_branch",
    "check_shopping_list",
)


class IntentAnchorValidator:
    """Refuse toute valeur non vérifiable dans la question."""

    def is_anchored(
        self,
        question: str,
        intent: QueryIntent,
    ) -> bool:
        """Vérifie les valeurs et les ambiguïtés de l'intention."""

        normalized = _normalize(question)

        if _contains_injection_marker(normalized):
            return False

        if _contains_conflicting_intentions(normalized):
            return False

        if isinstance(intent, UnsupportedIntent):
            return True

        if isinstance(intent, ProductListIntent):
            return _pagination_is_anchored(
                normalized,
                intent,
            )

        if isinstance(
            intent,
            (ProductDetailsIntent, StockByProductIntent),
        ):
            return _identifier_is_anchored(
                normalized,
                intent.product_id,
            )

        if isinstance(intent, StockByBranchIntent):
            return _identifier_is_anchored(
                normalized,
                intent.branch_id,
            )

        if isinstance(intent, ShoppingListIntent):
            return _shopping_list_is_anchored(
                normalized,
                intent,
            )

        return False


def _identifier_is_anchored(
    question: str,
    identifier: int,
) -> bool:
    """Exige un identifiant autonome et aucun autre nombre."""

    autonomous_numbers = {
        int(value)
        for value in _AUTONOMOUS_NUMBER_PATTERN.findall(question)
    }
    all_numbers = _positive_numbers(question)

    return (
        autonomous_numbers == {identifier}
        and all_numbers == [identifier]
    )


def _pagination_is_anchored(
    question: str,
    intent: ProductListIntent,
) -> bool:
    """Accepte les défauts ou une pagination explicitement nommée."""

    if _contains_negative_number(question):
        return False

    limits = _matched_values(question, _LIMIT_PATTERNS)
    offsets = _matched_values(question, _OFFSET_PATTERNS)

    if limits:
        if limits != {intent.limit}:
            return False
    elif intent.limit != 20:
        return False

    if offsets:
        if offsets != {intent.offset}:
            return False
    elif intent.offset != 0:
        return False

    all_numbers = set(_positive_numbers(question))
    anchored_numbers = limits | offsets

    return all_numbers == anchored_numbers


def _shopping_list_is_anchored(
    question: str,
    intent: ShoppingListIntent,
) -> bool:
    """Compare exactement les paires et tous les nombres présents."""

    if _contains_negative_number(question):
        return False

    extracted_pairs = _extract_pairs(question)
    expected_pairs = [
        (
            item.product_id,
            item.quantity,
        )
        for item in intent.items
    ]

    if extracted_pairs != expected_pairs:
        return False

    expected_numbers = Counter(
        value
        for pair in expected_pairs
        for value in pair
    )
    actual_numbers = Counter(_positive_numbers(question))

    return actual_numbers == expected_numbers


def _extract_pairs(question: str) -> list[tuple[int, int]]:
    """Extrait les paires reconnues en conservant leur ordre."""

    positioned_pairs: list[tuple[int, int, int]] = []

    for pattern in (
        _PRODUCT_FIRST_PAIR_PATTERN,
        _QUANTITY_FIRST_PAIR_PATTERN,
    ):
        for match in pattern.finditer(question):
            positioned_pairs.append(
                (
                    match.start(),
                    int(match.group("product_id")),
                    int(match.group("quantity")),
                )
            )

    positioned_pairs.sort(key=lambda pair: pair[0])

    return [
        (
            product_id,
            quantity,
        )
        for _, product_id, quantity in positioned_pairs
    ]


def _positive_numbers(question: str) -> list[int]:
    """Retourne les nombres positifs présents, signes inclus au contrôle."""

    return [
        int(value)
        for value in _SIGNED_NUMBER_PATTERN.findall(question)
        if not value.startswith("-")
    ]


def _contains_negative_number(question: str) -> bool:
    """Détecte toute valeur entière négative."""

    return any(
        value.startswith("-")
        for value in _SIGNED_NUMBER_PATTERN.findall(question)
    )


def _matched_values(
    question: str,
    patterns: tuple[re.Pattern[str], ...],
) -> set[int]:
    """Regroupe les valeurs explicitement associées à un marqueur."""

    return {
        int(match.group(1))
        for pattern in patterns
        for match in pattern.finditer(question)
    }


def _contains_injection_marker(question: str) -> bool:
    """Détecte les formulations visant le classificateur ou un outil."""

    return any(
        marker in question
        for marker in _INJECTION_MARKERS
    )


def _contains_conflicting_intentions(question: str) -> bool:
    """Détecte plusieurs familles d'actions explicites."""

    markers: set[str] = set()

    if any(
        marker in question
        for marker in (
            "details",
            "information",
            "prix du produit",
        )
    ):
        markers.add("product_details")

    if any(
        marker in question
        for marker in (
            "ou trouver",
            "disponible",
            "stock du produit",
            "reste t il",
        )
    ):
        markers.add("stock_by_product")

    if "branche" in question and any(
        marker in question
        for marker in (
            "stock",
            "contient",
            "produits",
        )
    ):
        markers.add("stock_by_branch")

    if (
        "produits" in question
        and "branche" not in question
        and any(
            marker in question
            for marker in (
                "liste",
                "affiche",
                "montre",
            )
        )
    ):
        markers.add("product_list")

    if (
        "liste d achats" in question
        or "ou acheter" in question
        or _PRODUCT_FIRST_PAIR_PATTERN.search(question)
        is not None
    ):
        markers.add("shopping_list")

    return len(markers) > 1


def _normalize(question: str) -> str:
    """Normalise le texte sans modifier les valeurs numériques."""

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
    normalized = re.sub(r"['’ʼ]", " ", normalized)

    return re.sub(r"\s+", " ", normalized).strip()
