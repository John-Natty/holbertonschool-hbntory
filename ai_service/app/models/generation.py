"""Contrat structuré des réponses conversationnelles générées."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.models.data import (
    BranchName,
    NonEmptyString,
    NonNegativeFiniteFloat,
    StrictBool,
    StrictModel,
    StrictNonNegativeInt,
    StrictPositiveInt,
)


GeneratedAnswerText = Annotated[
    str,
    Field(strict=True),
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=1200,
    ),
]


class ProductPriceClaim(StrictModel):
    """Lie un produit à son nom, son prix et sa devise."""

    type: Literal["product_price"] = "product_price"
    product_id: StrictPositiveInt
    product_name: NonEmptyString
    unit_price: NonNegativeFiniteFloat
    currency: NonEmptyString


class ProductListSummaryClaim(StrictModel):
    """Décrit sans ambiguïté la page de catalogue affichée."""

    type: Literal["product_list_summary"] = "product_list_summary"
    displayed_count: StrictNonNegativeInt
    total_count: StrictNonNegativeInt
    limit: StrictPositiveInt
    offset: StrictNonNegativeInt


class ProductStockSummaryClaim(StrictModel):
    """Décrit le nombre de branches où un produit est disponible."""

    type: Literal["product_stock_summary"] = "product_stock_summary"
    product_id: StrictPositiveInt
    available_branch_count: StrictNonNegativeInt


class ProductAvailabilityClaim(StrictModel):
    """Lie une disponibilité à un produit et à une branche précises."""

    type: Literal["product_availability"] = "product_availability"
    product_id: StrictPositiveInt
    branch_id: StrictPositiveInt | None = None
    branch_name: BranchName | None = None
    quantity: StrictNonNegativeInt | None = None
    available: StrictBool

    @model_validator(mode="after")
    def validate_availability_relation(self):
        """Refuse une disponibilité incohérente ou sans branche."""

        if self.branch_id is None and self.branch_name is None:
            raise ValueError(
                "Une disponibilité doit référencer une branche."
            )

        if self.available:
            if self.quantity is None or self.quantity == 0:
                raise ValueError(
                    "Une disponibilité positive exige une quantité."
                )
        elif self.quantity not in {None, 0}:
            raise ValueError(
                "Une indisponibilité ne peut pas avoir de stock positif."
            )

        return self


class BranchStockSummaryClaim(StrictModel):
    """Décrit le nombre de références d'une branche."""

    type: Literal["branch_stock_summary"] = "branch_stock_summary"
    branch_id: StrictPositiveInt
    branch_name: BranchName
    stock_count: StrictNonNegativeInt


class BranchStockItemClaim(StrictModel):
    """Lie une ligne de stock complète à sa branche."""

    type: Literal["branch_stock_item"] = "branch_stock_item"
    branch_id: StrictPositiveInt
    branch_name: BranchName
    product_id: StrictPositiveInt
    product_name: NonEmptyString
    quantity: StrictNonNegativeInt
    unit_price: NonNegativeFiniteFloat
    currency: NonEmptyString


class ShoppingClaimItem(StrictModel):
    """Conserve la relation demandé/disponible d'un article."""

    product_id: StrictPositiveInt
    requested_quantity: StrictPositiveInt
    available_quantity: StrictNonNegativeInt

    @model_validator(mode="after")
    def require_sufficient_quantity(self):
        """Une branche correspondante doit satisfaire chaque article."""

        if self.available_quantity < self.requested_quantity:
            raise ValueError(
                "La quantité disponible ne satisfait pas la demande."
            )

        return self


class ShoppingBranchClaim(StrictModel):
    """Lie une branche correspondante à tous les articles validés."""

    type: Literal["shopping_branch"] = "shopping_branch"
    branch_id: StrictPositiveInt
    branch_name: BranchName
    items: Annotated[
        list[ShoppingClaimItem],
        Field(min_length=1, max_length=100),
    ]


class ShoppingSummaryClaim(StrictModel):
    """Décrit le nombre de branches satisfaisant la liste."""

    type: Literal["shopping_summary"] = "shopping_summary"
    matching_branch_count: StrictNonNegativeInt


FactClaim = Annotated[
    ProductPriceClaim
    | ProductListSummaryClaim
    | ProductStockSummaryClaim
    | ProductAvailabilityClaim
    | BranchStockSummaryClaim
    | BranchStockItemClaim
    | ShoppingBranchClaim
    | ShoppingSummaryClaim,
    Field(discriminator="type"),
]


class NaturalSegment(StrictModel):
    """Autorise uniquement une courte transition sans fait métier."""

    type: Literal["natural"] = "natural"
    text: GeneratedAnswerText

    @field_validator("text")
    @classmethod
    def normalize_escaped_line_breaks(cls, value: str) -> str:
        """Normalise les sauts de ligne échappés par un fournisseur."""

        return value.replace("\\r\\n", "\n").replace("\\n", "\n")


class FactSegment(StrictModel):
    """Associe chaque phrase factuelle à une relation contrôlable."""

    type: Literal["fact"] = "fact"
    text: GeneratedAnswerText
    claim: FactClaim

    @field_validator("text")
    @classmethod
    def normalize_escaped_line_breaks(cls, value: str) -> str:
        """Normalise les sauts de ligne échappés par un fournisseur."""

        return value.replace("\\r\\n", "\n").replace("\\n", "\n")


AnswerSegment = Annotated[
    NaturalSegment | FactSegment,
    Field(discriminator="type"),
]


class GeneratedAnswer(StrictModel):
    """Contient des segments naturels et des faits explicitement liés."""

    segments: Annotated[
        list[AnswerSegment],
        Field(min_length=1, max_length=220),
    ]

    @model_validator(mode="after")
    def bound_public_answer(self):
        """Borne aussi la somme des segments pour protéger la mémoire."""

        if len(self.answer) > 8000:
            raise ValueError(
                "La réponse publique dépasse la taille autorisée."
            )

        return self

    @property
    def answer(self) -> str:
        """Assemble le texte public après validation des segments."""

        return "\n".join(segment.text for segment in self.segments)
