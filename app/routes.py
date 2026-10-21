"""
Flask routes.

CRUD (RESTful):
    GET    /inventory              list items (optional ?search=<text>)
    GET    /inventory/<id>         one item
    POST   /inventory              add an item
    PATCH  /inventory/<id>         update some fields of an item
    DELETE /inventory/<id>         remove an item

Misc:
    GET    /health                 liveness check
"""

from flask import Blueprint, jsonify, request

from app import data
from app.external_api import (
    ExternalAPIError,
    fetch_product_by_barcode,
    search_products_by_name,
)

bp = Blueprint("inventory", __name__)

# Text fields a client may set on an item (besides price and stock).
TEXT_FIELDS = [
    "barcode",
    "product_name",
    "brands",
    "ingredients_text",
    "categories",
    "quantity",
    "nutriscore_grade",
    "image_url",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def error(message, status):
    """Uniform JSON error body."""
    return jsonify({"error": message}), status


def parse_price(value):
    """Return price as a non-negative float rounded to 2dp, else raise ValueError."""
    if isinstance(value, bool):
        raise ValueError("price must be a number")
    price = float(value)
    if price < 0:
        raise ValueError("price cannot be negative")
    return round(price, 2)


def parse_stock(value):
    """Return stock as a non-negative int, else raise ValueError."""
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise ValueError("stock must be a whole number")
    stock = int(value)
    if stock < 0:
        raise ValueError("stock cannot be negative")
    return stock


def validate_fields(body, require_name):
    """
    Validate and clean an incoming JSON body.

    Returns (cleaned_dict, None) on success or (None, error_message) on failure.
    """
    if not isinstance(body, dict):
        return None, "Request body must be a JSON object."

    unknown = set(body) - set(TEXT_FIELDS) - {"price", "stock"}
    if unknown:
        return None, f"Unknown field(s): {', '.join(sorted(unknown))}."

    cleaned = {}
    for field in TEXT_FIELDS:
        if field in body:
            if not isinstance(body[field], str):
                return None, f"{field} must be a string."
            cleaned[field] = body[field].strip()

    if require_name and not cleaned.get("product_name"):
        return None, "product_name is required."
    if "product_name" in cleaned and not cleaned["product_name"]:
        return None, "product_name cannot be empty."

    try:
        if "price" in body:
            cleaned["price"] = parse_price(body["price"])
        if "stock" in body:
            cleaned["stock"] = parse_stock(body["stock"])
    except (TypeError, ValueError) as exc:
        return None, f"Invalid value: {exc}."

    return cleaned, None


def new_item(fields):
    """Build a complete inventory record with defaults for missing fields."""
    item = {"id": data.next_id()}
    for field in TEXT_FIELDS:
        item[field] = fields.get(field, "")
    item["price"] = fields.get("price", 0.0)
    item["stock"] = fields.get("stock", 0)
    return item


# --------------------------------------------------------------------------- #
# CRUD routes
# --------------------------------------------------------------------------- #
@bp.get("/inventory")
def list_items():
    """All items, optionally filtered by ?search= (name or brand, case-insensitive)."""
    term = request.args.get("search", "").strip().lower()
    items = data.inventory
    if term:
        items = [
            i for i in items
            if term in i["product_name"].lower() or term in i["brands"].lower()
        ]
    return jsonify(items), 200


@bp.get("/inventory/<int:item_id>")
def get_item(item_id):
    item = data.find_item(item_id)
    if item is None:
        return error(f"Item {item_id} not found.", 404)
    return jsonify(item), 200


@bp.post("/inventory")
def create_item():
    fields, problem = validate_fields(request.get_json(silent=True), require_name=True)
    if problem:
        return error(problem, 400)

    if fields.get("barcode") and any(
        i["barcode"] == fields["barcode"] for i in data.inventory
    ):
        return error(f"An item with barcode {fields['barcode']} already exists.", 409)

    item = new_item(fields)
    data.inventory.append(item)
    return jsonify(item), 201


@bp.patch("/inventory/<int:item_id>")
def update_item(item_id):
    item = data.find_item(item_id)
    if item is None:
        return error(f"Item {item_id} not found.", 404)

    fields, problem = validate_fields(request.get_json(silent=True), require_name=False)
    if problem:
        return error(problem, 400)
    if not fields:
        return error("No fields to update.", 400)

    item.update(fields)
    return jsonify(item), 200


@bp.delete("/inventory/<int:item_id>")
def delete_item(item_id):
    item = data.find_item(item_id)
    if item is None:
        return error(f"Item {item_id} not found.", 404)
    data.inventory.remove(item)
    return jsonify({"message": f"Item {item_id} deleted.", "item": item}), 200

# --------------------------------------------------------------------------- #
# OpenFoodFacts helper routes
# --------------------------------------------------------------------------- #
@bp.get("/external/barcode/<barcode>")
def external_by_barcode(barcode):
    """Look a product up on OpenFoodFacts without saving it."""
    try:
        product = fetch_product_by_barcode(barcode)
    except ValueError as exc:
        return error(str(exc), 400)
    except ExternalAPIError as exc:
        return error(str(exc), 502)
    if product is None:
        return error(f"No product found on OpenFoodFacts for barcode {barcode}.", 404)
    return jsonify(product), 200


@bp.get("/external/search")
def external_search():
    """Search OpenFoodFacts by name without saving anything."""
    try:
        products = search_products_by_name(request.args.get("name", ""))
    except ValueError as exc:
        return error(str(exc), 400)
    except ExternalAPIError as exc:
        return error(str(exc), 502)
    return jsonify(products), 200


@bp.post("/inventory/import")
def import_item():
    """
    Fetch a product from OpenFoodFacts by barcode and add it to the inventory.

    Body: {"barcode": "...", "price": 2.5, "stock": 10}
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not body.get("barcode"):
        return error("barcode is required.", 400)

    barcode = str(body["barcode"]).strip()
    if any(i["barcode"] == barcode for i in data.inventory):
        return error(f"An item with barcode {barcode} already exists.", 409)

    try:
        price = parse_price(body.get("price", 0))
        stock = parse_stock(body.get("stock", 0))
    except (TypeError, ValueError) as exc:
        return error(f"Invalid value: {exc}.", 400)

    try:
        product = fetch_product_by_barcode(barcode)
    except ValueError as exc:
        return error(str(exc), 400)
    except ExternalAPIError as exc:
        return error(str(exc), 502)
    if product is None:
        return error(f"No product found on OpenFoodFacts for barcode {barcode}.", 404)
    if not product["product_name"]:
        product["product_name"] = f"Product {barcode}"

    item = new_item({**product, "price": price, "stock": stock})
    data.inventory.append(item)
    return jsonify(item), 201


@bp.post("/inventory/<int:item_id>/enrich")
def enrich_item(item_id):
    """
    Fill in an existing item's empty fields from OpenFoodFacts using its
    barcode. Price and stock are never touched.
    """
    item = data.find_item(item_id)
    if item is None:
        return error(f"Item {item_id} not found.", 404)
    if not item.get("barcode"):
        return error("Item has no barcode to look up.", 400)

    try:
        product = fetch_product_by_barcode(item["barcode"])
    except ValueError as exc:
        return error(str(exc), 400)
    except ExternalAPIError as exc:
        return error(str(exc), 502)
    if product is None:
        return error(f"No product found on OpenFoodFacts for barcode {item['barcode']}.", 404)

    updated = []
    for field, value in product.items():
        if value and not item.get(field):
            item[field] = value
            updated.append(field)
    return jsonify({"item": item, "updated_fields": updated}), 200
@bp.get("/health")
def health():
    return jsonify({"status": "ok", "items": len(data.inventory)}), 200