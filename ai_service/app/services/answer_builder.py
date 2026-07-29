"""Construction déterministe des réponses publiques du service IA."""

from typing import Any

from app.models.conversation import generate_conversation_id
from app.models.data import (
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
)
from app.models.intents import (
    StockByProductIntent,
    UnsupportedIntent,
    UnsupportedReason,
)
from app.models.query import (
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    ProductDetailsResponse,
    ProductListResponse,
    ShoppingListResponse,
    StockByBranchResponse,
    StockByProductResponse,
    UnsupportedResponse,
)
from app.services.answer_generator import (
    branch_matches,
    get_stock_target,
    sanitize_business_text,
)


_ERROR_TEXTS: dict[ErrorCode, tuple[str, str]] = {
    "invalid_parameters": (
        "La demande contient des paramètres invalides.",
        "Les paramètres transmis à l'outil de données sont invalides.",
    ),
    "resource_not_found": (
        "La ressource demandée n’a pas été trouvée.",
        "Le produit ou la branche demandé n’existe pas.",
    ),
    "service_timeout": (
        "Le service de données a mis trop de temps à répondre.",
        "Le délai de réponse du serveur MCP est dépassé.",
    ),
    "service_unavailable": (
        "Le service de données est temporairement indisponible.",
        "Le serveur MCP n’est pas connecté.",
    ),
    "invalid_service_response": (
        "Le service de données a retourné une réponse invalide.",
        "La réponse du serveur MCP ne respecte pas le contrat attendu.",
    ),
    "client_error": (
        "Le service de données n’a pas pu traiter la demande.",
        "Une erreur métier du serveur MCP empêche le traitement.",
    ),
    "internal_error": (
        "Une erreur interne empêche le traitement de la demande.",
        "Le service IA a rencontré une erreur inattendue.",
    ),
}

_UNSUPPORTED_TEXTS: dict[UnsupportedReason, str] = {
    "out_of_domain": (
        "Je peux uniquement répondre aux questions concernant les produits, "
        "les stocks, les branches et les listes d’achats de HBntory."
    ),
    "missing_product_id": (
        "Veuillez préciser l’identifiant du produit."
    ),
    "missing_branch_id": (
        "Veuillez préciser le nom ou l’identifiant de la branche."
    ),
    "missing_items": (
        "Veuillez préciser les produits et les quantités de votre liste."
    ),
    "read_only": (
        "Cette demande n’est pas disponible : HBntory permet uniquement "
        "de consulter les produits, les stocks, les branches et les listes "
        "d’achats."
    ),
    "ambiguous": (
        "Veuillez formuler une seule demande avec les identifiants et les "
        "quantités nécessaires."
    ),
    "unrecognized": (
        "Je peux uniquement répondre aux questions concernant les produits, "
        "les stocks, les branches et les listes d’achats de HBntory."
    ),
}


class AnswerBuilder:
    """Produit uniquement des textes fondés sur des modèles validés."""

    def product_list(
        self,
        data: ProductListData,
        *,
        conversation_id: str | None = None,
    ) -> ProductListResponse:
        """Présente la page Produit sans effectuer d'autre appel."""

        displayed_products = data.products[:data.limit]
        product_count = len(displayed_products)

        if product_count == 0:
            answer = "Aucun produit n’a été trouvé."
        else:
            if data.offset > 0 or product_count < data.count:
                product_label = (
                    "produit affiché"
                    if product_count == 1
                    else "produits affichés"
                )
                heading = (
                    f"Voici {product_count} {product_label} "
                    f"sur {data.count} au total :"
                )
            elif product_count == 1:
                heading = "1 produit a été trouvé :"
            else:
                heading = (
                    f"{product_count} produits ont été trouvés :"
                )

            product_lines = "\n".join(
                (
                    f"- #{product.id} — "
                    f"{sanitize_business_text(product.name)} — "
                    f"{_format_price(product.unit_price)} "
                    f"{sanitize_business_text(product.currency, 12)}"
                )
                for product in displayed_products
            )
            answer = f"{heading}\n\n{product_lines}"

        return ProductListResponse(
            answer=answer,
            data=data,
            **_conversation_fields(
                ProductListResponse,
                conversation_id,
            ),
        )

    def product_details(
        self,
        data: ProductDetailsData,
        *,
        conversation_id: str | None = None,
    ) -> ProductDetailsResponse:
        """Construit la réponse détaillée d'un produit."""

        product = data.product
        price = _format_price(product.unit_price)
        answer = (
            f"Le produit {product.id} est "
            f"« {sanitize_business_text(product.name)} » "
            f"et coûte {price} "
            f"{sanitize_business_text(product.currency, 12)}."
        )

        return ProductDetailsResponse(
            answer=answer,
            data=data,
            **_conversation_fields(
                ProductDetailsResponse,
                conversation_id,
            ),
        )

    def stock_by_product(
        self,
        data: StockByProductData,
        intent: StockByProductIntent | None = None,
        *,
        conversation_id: str | None = None,
    ) -> StockByProductResponse:
        """Construit la réponse de disponibilité d'un produit."""

        target_id, target_name = get_stock_target(intent)
        if target_id is not None or target_name is not None:
            answer = _targeted_stock_answer(
                data,
                target_id,
                target_name,
            )
        else:
            available_branches = [
                branch
                for branch in data.branches
                if branch.quantity > 0
            ]
            branch_count = len(available_branches)

            if branch_count == 0:
                answer = (
                    f"Le produit {data.product_id} n’est disponible "
                    "dans aucune branche."
                )
            elif branch_count == 1:
                branch = available_branches[0]
                answer = (
                    f"Le produit {data.product_id} est disponible "
                    f"dans la branche "
                    f"{sanitize_business_text(branch.branch_name, 100)}, "
                    f"avec {branch.quantity} unité"
                    f"{'' if branch.quantity == 1 else 's'} en stock."
                )
            else:
                heading = (
                    f"Le produit {data.product_id} est disponible "
                    f"dans {branch_count} branches :"
                )
                branch_lines = "\n".join(
                    (
                        f"- "
                        f"{sanitize_business_text(
                            branch.branch_name,
                            100,
                        )} : "
                        f"{branch.quantity} unité"
                        f"{'' if branch.quantity == 1 else 's'}"
                    )
                    for branch in available_branches
                )
                answer = f"{heading}\n{branch_lines}"

        return StockByProductResponse(
            answer=answer,
            data=data,
            **_conversation_fields(
                StockByProductResponse,
                conversation_id,
            ),
        )

    def stock_by_branch(
        self,
        data: StockByBranchData,
        *,
        conversation_id: str | None = None,
    ) -> StockByBranchResponse:
        """Construit la réponse de contenu d'une branche."""

        branch_name = sanitize_business_text(
            data.branch.name,
            100,
        )

        if not data.stocks:
            answer = (
                f"La branche {branch_name} ne possède actuellement "
                "aucun produit en stock."
            )
        else:
            stock_count = len(data.stocks)
            if stock_count == 1:
                heading = (
                    f"La branche {branch_name} possède "
                    "1 référence en stock :"
                )
            else:
                heading = (
                    f"La branche {branch_name} possède "
                    f"{stock_count} références en stock :"
                )

            stock_lines = "\n".join(
                (
                    f"- Produit n°{stock.product_id} — "
                    f"Quantité : {stock.quantity} — "
                    f"Nom : "
                    f"{sanitize_business_text(stock.product_name)} — "
                    f"Prix unitaire : "
                    f"{_format_price(stock.unit_price)} "
                    f"{sanitize_business_text(
                        stock.currency,
                        12,
                    )}"
                )
                for stock in data.stocks
            )
            answer = f"{heading}\n{stock_lines}"

        return StockByBranchResponse(
            answer=answer,
            data=data,
            **_conversation_fields(
                StockByBranchResponse,
                conversation_id,
            ),
        )

    def shopping_list(
        self,
        data: ShoppingListData,
        *,
        conversation_id: str | None = None,
    ) -> ShoppingListResponse:
        """Construit la réponse d'une liste d'achats."""

        branch_count = len(data.matching_branches)

        if branch_count == 0:
            answer = (
                "Aucune branche ne peut satisfaire entièrement "
                "cette liste d’achats."
            )
        else:
            branch_names = [
                sanitize_business_text(
                    branch.branch_name,
                    100,
                )
                for branch in data.matching_branches
            ]
            joined_names = _join_french_list(branch_names)

        if branch_count == 1:
            answer = (
                f"La branche {joined_names} peut satisfaire entièrement "
                "cette liste d’achats."
            )
        elif branch_count > 1:
            answer = (
                f"Les branches {joined_names} peuvent satisfaire "
                "entièrement cette liste d’achats."
            )

        return ShoppingListResponse(
            answer=answer,
            data=data,
            **_conversation_fields(
                ShoppingListResponse,
                conversation_id,
            ),
        )

    def unsupported(
        self,
        intent: UnsupportedIntent,
        *,
        conversation_id: str | None = None,
    ) -> UnsupportedResponse:
        """Construit un refus déterministe selon la cause validée."""

        return UnsupportedResponse(
            answer=_UNSUPPORTED_TEXTS[intent.reason_code],
            **_conversation_fields(
                UnsupportedResponse,
                conversation_id,
            ),
        )

    def error(
        self,
        code: ErrorCode,
        *,
        conversation_id: str | None = None,
    ) -> ErrorResponse:
        """Construit une erreur publique sans détail interne."""

        answer, message = _ERROR_TEXTS[code]

        return ErrorResponse(
            answer=answer,
            error=ErrorDetail(
                code=code,
                message=message,
            ),
            **_conversation_fields(
                ErrorResponse,
                conversation_id,
            ),
        )


def _join_french_list(values: list[str]) -> str:
    """Joint une liste non vide avec une conjonction française."""

    if len(values) == 1:
        return values[0]

    return f"{', '.join(values[:-1])} et {values[-1]}"


def _targeted_stock_answer(
    data: StockByProductData,
    target_id: int | None,
    target_name: str | None,
) -> str:
    """Répond à la branche demandée depuis l'unique résultat produit."""

    matching_branch = next(
        (
            branch
            for branch in data.branches
            if branch_matches(
                branch.branch_id,
                branch.branch_name,
                target_id,
                target_name,
            )
        ),
        None,
    )
    if matching_branch is not None:
        branch_label = sanitize_business_text(
            matching_branch.branch_name,
            100,
        )
    elif target_name is not None:
        branch_label = sanitize_business_text(
            target_name,
            100,
        )
    else:
        branch_label = f"n°{target_id}"

    if (
        matching_branch is not None
        and matching_branch.quantity > 0
    ):
        return (
            f"Le produit {data.product_id} est disponible dans la "
            f"branche {branch_label}, avec "
            f"{matching_branch.quantity} unité"
            f"{'' if matching_branch.quantity == 1 else 's'} "
            "en stock."
        )

    answer = (
        f"Le produit {data.product_id} n’est pas disponible dans la "
        f"branche {branch_label}."
    )
    alternatives = [
        branch
        for branch in data.branches
        if branch.quantity > 0
        and (
            matching_branch is None
            or branch.branch_id != matching_branch.branch_id
        )
    ]
    if not alternatives:
        return answer

    if len(alternatives) == 1:
        branch = alternatives[0]
        return (
            f"{answer} Il est toutefois disponible dans la branche "
            f"{sanitize_business_text(branch.branch_name, 100)}, "
            f"avec {branch.quantity} unité"
            f"{'' if branch.quantity == 1 else 's'} en stock."
        )

    branch_lines = "\n".join(
        (
            f"- {sanitize_business_text(branch.branch_name, 100)} : "
            f"{branch.quantity} unité"
            f"{'' if branch.quantity == 1 else 's'}"
        )
        for branch in alternatives
    )
    return (
        f"{answer} Il reste toutefois disponible dans ces branches :"
        f"\n{branch_lines}"
    )


def _conversation_fields(
    response_model: Any,
    conversation_id: str | None,
) -> dict[str, str]:
    """Ajoute l'identifiant public, avec un repli UUID sécurisé."""

    if "conversation_id" not in response_model.model_fields:
        return {}

    return {
        "conversation_id": (
            conversation_id
            if conversation_id is not None
            else generate_conversation_id()
        )
    }


def _format_price(price: float) -> str:
    """Formate un prix validé avec deux décimales en français."""

    return f"{price:.2f}".replace(".", ",")
