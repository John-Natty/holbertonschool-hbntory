"""Construction déterministe des réponses publiques du service IA."""

from app.models.data import (
    ProductDetailsData,
    ProductListData,
    ShoppingListData,
    StockByBranchData,
    StockByProductData,
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
    TextResponse,
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


class AnswerBuilder:
    """Produit uniquement des textes fondés sur des modèles validés."""

    def product_list(
        self,
        data: ProductListData,
    ) -> ProductListResponse:
        """Construit la réponse d'une page Produit."""

        product_count = len(data.products)

        if product_count == 0:
            answer = "Aucun produit n’a été trouvé."
        elif product_count == 1:
            answer = "1 produit a été trouvé."
        else:
            answer = f"{product_count} produits ont été trouvés."

        return ProductListResponse(
            answer=answer,
            data=data,
        )

    def product_details(
        self,
        data: ProductDetailsData,
    ) -> ProductDetailsResponse:
        """Construit la réponse détaillée d'un produit."""

        product = data.product
        price = f"{product.unit_price:.2f}".replace(".", ",")
        answer = (
            f"Le produit {product.id} est « {product.name} » "
            f"et coûte {price} {product.currency}."
        )

        return ProductDetailsResponse(
            answer=answer,
            data=data,
        )

    def stock_by_product(
        self,
        data: StockByProductData,
    ) -> StockByProductResponse:
        """Construit la réponse de disponibilité d'un produit."""

        branch_count = len(data.branches)

        if branch_count == 0:
            answer = (
                f"Le produit {data.product_id} n’est disponible "
                "dans aucune branche."
            )
        elif branch_count == 1:
            answer = (
                f"Le produit {data.product_id} est disponible "
                "dans 1 branche."
            )
        else:
            answer = (
                f"Le produit {data.product_id} est disponible "
                f"dans {branch_count} branches."
            )

        return StockByProductResponse(
            answer=answer,
            data=data,
        )

    def stock_by_branch(
        self,
        data: StockByBranchData,
    ) -> StockByBranchResponse:
        """Construit la réponse de contenu d'une branche."""

        branch_name = data.branch.name

        if not data.stocks:
            answer = (
                f"La branche {branch_name} ne possède actuellement "
                "aucun produit en stock."
            )
        else:
            stock_lines = "\n".join(
                (
                    f"- produit {stock.product_id} : "
                    f"{stock.quantity} "
                    f"{'unité' if stock.quantity == 1 else 'unités'}"
                )
                for stock in data.stocks
            )
            answer = f"La branche {branch_name} possède :\n{stock_lines}"

        return StockByBranchResponse(
            answer=answer,
            data=data,
        )

    def shopping_list(
        self,
        data: ShoppingListData,
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
                branch.branch_name
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
        )

    def unsupported(self) -> TextResponse:
        """Explique les formats compris sans affirmer de fait métier."""

        return TextResponse(
            answer=(
                "Je n’ai pas compris la demande. Demandez une seule "
                "action avec un identifiant numérique, par exemple "
                "« stock du produit 12 », ou utilisez « liste "
                "d’achats : produit 12 x2 »."
            )
        )

    def error(
        self,
        code: ErrorCode,
    ) -> ErrorResponse:
        """Construit une erreur publique sans détail interne."""

        answer, message = _ERROR_TEXTS[code]

        return ErrorResponse(
            answer=answer,
            error=ErrorDetail(
                code=code,
                message=message,
            ),
        )


def _join_french_list(values: list[str]) -> str:
    """Joint une liste non vide avec une conjonction française."""

    if len(values) == 1:
        return values[0]

    return f"{', '.join(values[:-1])} et {values[-1]}"
