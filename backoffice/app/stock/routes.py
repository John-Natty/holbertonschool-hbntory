"""Routes permettant à un common user de gérer le stock de sa branche."""

from pathlib import Path

from flask import (
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from app.auth.decorators import own_branch_required
from app.services import product_api, stock_operations
from app.services.stock_validation import StockError
from app.stock import stock_bp
from app.stock.forms import StockMovementForm

# Taille de page maximale acceptée par l'API Produit.
_PAGE_SIZE = 100

# Nombre de pages maximum lues, garde-fou contre une pagination anormale.
_MAX_PAGES = 10


def describe_product(product_id: int) -> str:
    """Retourne le nom d'un produit, ou son identifiant si l'API échoue."""

    # L'affichage ne doit jamais casser à cause de l'API Produit.
    try:
        product = product_api.get_product(product_id)

    except product_api.ProductApiError:
        return f"Produit {product_id}"

    return product.get("name") or f"Produit {product_id}"


def fetch_all_products() -> list[dict]:
    """Retourne le catalogue complet en paginant l'API Produit."""

    products: list[dict] = []
    offset = 0

    for _ in range(_MAX_PAGES):
        page = product_api.list_products(
            limit=_PAGE_SIZE,
            offset=offset,
        )

        results = page.get("results")

        if not isinstance(results, list):
            raise product_api.ProductApiError(
                "La liste de produits retournée est invalide."
            )

        if not results:
            break

        if not all(isinstance(product, dict) for product in results):
            raise product_api.ProductApiError(
                "Un produit retourné par l'API est invalide."
            )

        products.extend(results)

        # La dernière page est plus courte que la taille demandée.
        if len(results) < _PAGE_SIZE:
            break

        offset += _PAGE_SIZE

    return products


def _image_names(folder: str) -> set[str]:
    """Retourne les noms de fichiers d'images présents dans un dossier."""

    path = Path(current_app.static_folder) / "img" / folder

    if not path.is_dir():
        return set()

    return {image.stem for image in path.glob("*.webp")}


def _card_image(
    product: dict,
    product_images: set[str],
    category_images: set[str],
) -> str:
    """Retourne l'illustration d'un produit, sa famille, ou le repli."""

    if str(product.get("id")) in product_images:
        return f"img/products/{product['id']}.webp"

    # Le nom de fichier d'une catégorie dérive de son libellé :
    # « Development Kits » donne « development-kits ».
    category = str(product.get("category") or "")
    slug = category.lower().replace(" ", "-")

    if slug in category_images:
        return f"img/categories/{slug}.webp"

    return "img/categories/default.webp"


def build_catalog(branch_id: int) -> tuple[list[dict], list[dict]]:
    """Sépare le catalogue en produits présents puis absents de la branche."""

    quantities = {
        line.product_id: line.quantity
        for line in stock_operations.list_stock(branch_id)
    }

    try:
        products = fetch_all_products()

    except product_api.ProductApiError:
        flash(
            "L'API Produit est injoignable, le catalogue est incomplet.",
            "danger",
        )

        # Sans catalogue, seules les lignes de stock restent affichables.
        products = [
            {
                "id": product_id,
                "name": describe_product(product_id),
                "category": "",
            }
            for product_id in sorted(quantities)
        ]

    product_images = _image_names("products")
    category_images = _image_names("categories")

    in_stock: list[dict] = []
    missing: list[dict] = []

    for product in products:
        product_id = product.get("id")

        if not isinstance(product_id, int):
            continue

        quantity = quantities.get(product_id, 0)

        card = {
            "id": product_id,
            "name": product.get("name") or f"Produit {product_id}",
            "unit_price": product.get("unit_price"),
            "currency": product.get("currency") or "",
            "quantity": quantity,
            "image": _card_image(
                product,
                product_images,
                category_images,
            ),
        }

        if quantity > 0:
            in_stock.append(card)
        else:
            missing.append(card)

    in_stock.sort(key=lambda card: card["name"].lower())
    missing.sort(key=lambda card: card["name"].lower())

    return in_stock, missing


def render_stock_page(branch_id: int) -> str:
    """Affiche le catalogue de la branche sous forme de cartes."""

    in_stock, missing = build_catalog(branch_id)

    return render_template(
        "stock/list.html",
        in_stock=in_stock,
        missing=missing,
        branch_id=branch_id,
    )


def render_stock_form_page(branch_id: int, form: StockMovementForm) -> str:
    """Affiche le catalogue en conservant les erreurs d'un formulaire."""

    for field in (form.product_id, form.amount):
        for error in field.errors:
            flash(error, "danger")

    return render_stock_page(branch_id)


@stock_bp.route("/<int:branch_id>/stock")
@own_branch_required
def list_branch_stock(branch_id: int) -> str:
    """Affiche le stock de la branche de l'utilisateur connecté."""

    return render_stock_page(branch_id)


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
        return render_stock_form_page(branch_id, form)

    # Refuse un identifiant qui ne correspond à aucun produit connu.
    try:
        product_api.get_product(form.product_id.data)

    except product_api.ProductNotFoundError:
        flash(
            "Aucun produit ne correspond à cet identifiant.",
            "danger",
        )

        return render_stock_page(branch_id)

    except product_api.ProductApiError:
        flash(
            "L'API Produit est injoignable, réessayez plus tard.",
            "danger",
        )

        return render_stock_page(branch_id)

    try:
        stock_operations.add_stock(
            branch_id,
            form.product_id.data,
            form.amount.data,
        )

    except StockError as error:
        flash(str(error), "danger")

        return render_stock_page(branch_id)

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
        return render_stock_form_page(branch_id, form)

    # Le produit est déjà en stock, son existence n'est pas revérifiée.
    try:
        stock_operations.remove_stock(
            branch_id,
            form.product_id.data,
            form.amount.data,
        )

    except StockError as error:
        flash(str(error), "danger")

        return render_stock_page(branch_id)

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


def _read_movement(payload: dict) -> tuple[int, int] | None:
    """Extrait un identifiant de produit et une quantité signée valides."""

    product_id = payload.get("product_id")
    amount = payload.get("amount")

    # « True » est un entier en Python : il doit être refusé explicitement.
    for value in (product_id, amount):
        if isinstance(value, bool) or not isinstance(value, int):
            return None

    if product_id < 1 or amount == 0:
        return None

    return product_id, amount


@stock_bp.route(
    "/<int:branch_id>/stock/move",
    methods=["POST"],
)
@own_branch_required
def move_branch_stock(branch_id: int) -> tuple[Response, int] | Response:
    """Applique un mouvement de stock et retourne la nouvelle quantité."""

    movement = _read_movement(request.get_json(silent=True) or {})

    if movement is None:
        return jsonify(
            success=False,
            message="Mouvement de stock invalide.",
        ), 400

    product_id, amount = movement

    # Un ajout peut faire entrer un produit inconnu dans la branche.
    if amount > 0:
        try:
            product_api.get_product(product_id)

        except product_api.ProductNotFoundError:
            return jsonify(
                success=False,
                message="Aucun produit ne correspond à cet identifiant.",
            ), 404

        except product_api.ProductApiError:
            return jsonify(
                success=False,
                message="L'API Produit est injoignable.",
            ), 503

    try:
        if amount > 0:
            stock = stock_operations.add_stock(
                branch_id,
                product_id,
                amount,
            )
        else:
            stock = stock_operations.remove_stock(
                branch_id,
                product_id,
                -amount,
            )

    except StockError as error:
        # Renvoie la quantité réelle pour que la carte se recale.
        return jsonify(
            success=False,
            message=str(error),
            quantity=stock_operations.get_stock_quantity(
                branch_id,
                product_id,
            ),
        ), 409

    return jsonify(
        success=True,
        quantity=stock.quantity,
    )
