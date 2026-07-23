"""Routes permettant à un common user de gérer le stock de sa branche."""

from flask import Response, flash, redirect, render_template, url_for

from app.auth.decorators import own_branch_required
from app.services import product_api, stock_operations
from app.services.stock_validation import StockError
from app.stock import stock_bp
from app.stock.forms import StockMovementForm


def describe_product(product_id: int) -> str:
    """Retourne le nom d'un produit, ou son identifiant si l'API échoue."""

    # L'affichage ne doit jamais casser à cause de l'API Produit.
    try:
        product = product_api.get_product(product_id)

    except product_api.ProductApiError:
        return f"Produit {product_id}"

    return product.get("name") or f"Produit {product_id}"


def build_stock_rows(branch_id: int) -> list[dict]:
    """Retourne les lignes de stock enrichies du nom de chaque produit."""

    return [
        {
            "product_id": line.product_id,
            "name": describe_product(line.product_id),
            "quantity": line.quantity,
        }
        for line in stock_operations.list_stock(branch_id)
    ]


def render_stock_page(branch_id: int, form: StockMovementForm) -> str:
    """Affiche la page de stock d'une branche avec son formulaire."""

    return render_template(
        "stock/list.html",
        rows=build_stock_rows(branch_id),
        form=form,
        branch_id=branch_id,
    )


@stock_bp.route("/<int:branch_id>/stock")
@own_branch_required
def list_branch_stock(branch_id: int) -> str:
    """Affiche le stock de la branche de l'utilisateur connecté."""

    return render_stock_page(branch_id, StockMovementForm())


@stock_bp.route(
    "/<int:branch_id>/stock/add",
    methods=["POST"],
)
@own_branch_required
def add_branch_stock(branch_id: int) -> str | Response:
    """Ajoute une quantité de produit au stock de la branche."""

    form = StockMovementForm()

    # Vérifie les champs et le jeton CSRF.
    if not form.validate_on_submit():
        return render_stock_page(branch_id, form)

    # Refuse un identifiant qui ne correspond à aucun produit connu.
    try:
        product_api.get_product(form.product_id.data)

    except product_api.ProductNotFoundError:
        form.product_id.errors.append(
            "Aucun produit ne correspond à cet identifiant."
        )

        return render_stock_page(branch_id, form)

    except product_api.ProductApiError:
        flash(
            "L'API Produit est injoignable, réessayez plus tard.",
            "danger",
        )

        return render_stock_page(branch_id, form)

    try:
        stock_operations.add_stock(
            branch_id,
            form.product_id.data,
            form.amount.data,
        )

    except StockError as error:
        flash(str(error), "danger")

        return render_stock_page(branch_id, form)

    flash(
        f"{form.amount.data} unité(s) ajoutée(s) au stock.",
        "success",
    )

    return redirect(
        url_for(
            "stock.list_branch_stock",
            branch_id=branch_id,
        )
    )


@stock_bp.route(
    "/<int:branch_id>/stock/remove",
    methods=["POST"],
)
@own_branch_required
def remove_branch_stock(branch_id: int) -> str | Response:
    """Retire une quantité de produit du stock de la branche."""

    form = StockMovementForm()

    if not form.validate_on_submit():
        return render_stock_page(branch_id, form)

    # Le produit est déjà en stock, son existence n'est pas revérifiée.
    try:
        stock_operations.remove_stock(
            branch_id,
            form.product_id.data,
            form.amount.data,
        )

    except StockError as error:
        flash(str(error), "danger")

        return render_stock_page(branch_id, form)

    flash(
        f"{form.amount.data} unité(s) retirée(s) du stock.",
        "success",
    )

    return redirect(
        url_for(
            "stock.list_branch_stock",
            branch_id=branch_id,
        )
    )
