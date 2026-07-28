"""État conversationnel court, strict et indépendant des réponses MCP."""

from __future__ import annotations

import re
import secrets
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, TypeAdapter

from app.models.data import (
    BranchName,
    StrictModel,
    StrictNonNegativeInt,
    StrictPositiveInt,
)
from app.models.mcp import ShoppingListItem


ConversationId = Annotated[
    str,
    Field(strict=True),
    StringConstraints(
        min_length=32,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]

ConversationIntentType = Literal[
    "product_list",
    "product_details",
    "stock_by_product",
    "stock_by_branch",
    "shopping_list",
]

CONVERSATION_ID_ADAPTER = TypeAdapter(ConversationId)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:api[_ -]?key|token|secret|password|authorization)"
    r"\s*[:=]\s*[^\s,;]+"
)
_BEARER_PATTERN = re.compile(
    r"(?i)\b(?:authorization\s*[:=]?\s*)?bearer\s+"
    r"[A-Za-z0-9._~+/=-]{8,}"
)
_KNOWN_TOKEN_PATTERN = re.compile(
    r"(?i)\b(?:sk|nvapi|ghp|github_pat|xox[baprs])[-_]"
    r"[A-Za-z0-9._-]{8,}\b"
)
_JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\."
    r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_REDACTION = "[donnée sensible masquée]"


class ConversationTurn(StrictModel):
    """Conserve uniquement les textes publics bornés d'un échange."""

    user: Annotated[
        str,
        Field(strict=True, min_length=1, max_length=2000),
    ]
    assistant: Annotated[
        str,
        Field(strict=True, min_length=1, max_length=8000),
    ]


class ReducedBranchStock(StrictModel):
    """Résumé minimal d'une disponibilité, sans réponse MCP brute."""

    branch_id: StrictPositiveInt
    branch_name: BranchName
    quantity: StrictNonNegativeInt


class ReducedMatchingBranch(StrictModel):
    """Résumé minimal d'une branche satisfaisant une liste d'achats."""

    branch_id: StrictPositiveInt
    branch_name: BranchName


class ConversationObservation(StrictModel):
    """Faits réduits qu'un tour réussi autorise à mémoriser."""

    intent: ConversationIntentType
    product_id: StrictPositiveInt | None = None
    branch_id: StrictPositiveInt | None = None
    branch_name: BranchName | None = None
    product_ids: Annotated[
        list[StrictPositiveInt],
        Field(default_factory=list, max_length=100),
    ]
    shopping_items: Annotated[
        list[ShoppingListItem],
        Field(default_factory=list, max_length=100),
    ]
    stock_branches: Annotated[
        list[ReducedBranchStock],
        Field(default_factory=list, max_length=100),
    ]
    matching_branches: Annotated[
        list[ReducedMatchingBranch],
        Field(default_factory=list, max_length=100),
    ]


class ConversationState(StrictModel):
    """Mémoire utile au prochain tour, volontairement petite."""

    turns: Annotated[
        list[ConversationTurn],
        Field(default_factory=list, max_length=50),
    ]
    last_intent: ConversationIntentType | None = None
    last_product_id: StrictPositiveInt | None = None
    last_branch_id: StrictPositiveInt | None = None
    last_branch_name: BranchName | None = None
    last_product_ids: Annotated[
        list[StrictPositiveInt],
        Field(default_factory=list, max_length=100),
    ]
    shopping_items: Annotated[
        list[ShoppingListItem],
        Field(default_factory=list, max_length=100),
    ]
    last_stock_branches: Annotated[
        list[ReducedBranchStock],
        Field(default_factory=list, max_length=100),
    ]
    last_matching_branches: Annotated[
        list[ReducedMatchingBranch],
        Field(default_factory=list, max_length=100),
    ]

    def apply(self, observation: ConversationObservation) -> None:
        """Remplace seulement l'état pertinent avec des faits réduits."""

        self.last_intent = observation.intent

        if observation.intent == "product_list":
            self.last_product_id = None
            self.last_branch_id = None
            self.last_branch_name = None
            self.last_product_ids = list(observation.product_ids)
            self.shopping_items = []
            self.last_stock_branches = []
            self.last_matching_branches = []
            return

        if observation.intent == "product_details":
            self.last_product_id = observation.product_id
            self.last_branch_id = None
            self.last_branch_name = None
            self.shopping_items = []
            self.last_stock_branches = []
            self.last_matching_branches = []
            return

        if observation.intent == "stock_by_product":
            self.last_product_id = observation.product_id
            self.last_branch_id = observation.branch_id
            self.last_branch_name = observation.branch_name
            self.shopping_items = []
            self.last_stock_branches = list(
                observation.stock_branches
            )
            self.last_matching_branches = []
            return

        if observation.intent == "stock_by_branch":
            self.last_product_id = None
            self.last_branch_id = observation.branch_id
            self.last_branch_name = observation.branch_name
            self.last_product_ids = list(observation.product_ids)
            self.shopping_items = []
            self.last_stock_branches = []
            self.last_matching_branches = []
            return

        self.last_product_id = None
        self.last_branch_id = None
        self.last_branch_name = None
        self.shopping_items = list(observation.shopping_items)
        self.last_stock_branches = []
        self.last_matching_branches = list(
            observation.matching_branches
        )

    def prompt_context(self) -> dict[str, object]:
        """Produit une vue bornée et sûre destinée à la compréhension."""

        return self.model_dump(mode="json")


def generate_conversation_id() -> ConversationId:
    """Génère un jeton opaque, aléatoire et compatible avec une URL."""

    return CONVERSATION_ID_ADAPTER.validate_python(
        secrets.token_urlsafe(32)
    )


def validate_conversation_id(value: str) -> ConversationId:
    """Valide un identifiant reçu sans le normaliser silencieusement."""

    return CONVERSATION_ID_ADAPTER.validate_python(value)


def redact_sensitive_text(value: str, max_length: int) -> str:
    """Masque les secrets et URLs avant mémoire ou envoi au modèle."""

    redacted = _BEARER_PATTERN.sub(_REDACTION, value)
    redacted = _SENSITIVE_ASSIGNMENT_PATTERN.sub(_REDACTION, redacted)
    redacted = _KNOWN_TOKEN_PATTERN.sub(_REDACTION, redacted)
    redacted = _JWT_PATTERN.sub(_REDACTION, redacted)
    redacted = _URL_PATTERN.sub(_REDACTION, redacted)
    return redacted[:max_length]
