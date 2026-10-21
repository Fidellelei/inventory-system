"""
OpenFoodFacts client.

Two lookups are supported:
  * fetch_product_by_barcode(barcode)  -> one product (or None if unknown)
  * search_products_by_name(name)      -> a short list of matching products

Raw OpenFoodFacts records carry hundreds of fields, so every result is
reduced to the handful this inventory stores (see `normalize_product`).
Network or upstream failures are raised as `ExternalAPIError` so callers can
turn them into clean HTTP / CLI error messages.
"""

import requests

BASE_URL = "https://world.openfoodfacts.org"
TIMEOUT = 10  # seconds

# OpenFoodFacts asks every client to identify itself with a User-Agent.
HEADERS = {"User-Agent": "InventoryManagementLab/1.0 (student project)"}

# The fields we keep from an OpenFoodFacts product record.
PRODUCT_FIELDS = [
    "product_name",
    "brands",
    "ingredients_text",
    "categories",
    "quantity",
    "nutriscore_grade",
    "image_url",
]


class ExternalAPIError(Exception):
    """Raised when OpenFoodFacts cannot be reached or returns an error."""


def normalize_product(raw, barcode=None):
    """Reduce a raw OpenFoodFacts product dict to the fields we store."""
    product = {field: raw.get(field) or "" for field in PRODUCT_FIELDS}
    product["barcode"] = barcode or raw.get("code") or raw.get("_id") or ""
    return product


def fetch_product_by_barcode(barcode):
    """
    Look up one product by barcode.

    Returns a normalised product dict, or None when OpenFoodFacts has no
    product with that barcode (their response has "status": 0).
    """
    barcode = str(barcode).strip()
    if not barcode.isdigit():
        raise ValueError("Barcode must contain digits only.")

    url = f"{BASE_URL}/api/v2/product/{barcode}.json"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ExternalAPIError(f"Could not reach OpenFoodFacts: {exc}") from exc

    # OpenFoodFacts answers 404 with {"status": 0} for unknown barcodes.
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise ExternalAPIError(f"OpenFoodFacts returned HTTP {response.status_code}.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ExternalAPIError("OpenFoodFacts returned invalid JSON.") from exc

    if payload.get("status") != 1 or "product" not in payload:
        return None
    return normalize_product(payload["product"], barcode=barcode)


def search_products_by_name(name, page_size=5):
    """Search OpenFoodFacts by product name; returns a list of normalised products."""
    name = (name or "").strip()
    if not name:
        raise ValueError("A product name is required for searching.")

    url = f"{BASE_URL}/cgi/search.pl"
    params = {
        "search_terms": name,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": page_size,
    }
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ExternalAPIError(f"Could not reach OpenFoodFacts: {exc}") from exc

    if response.status_code != 200:
        raise ExternalAPIError(f"OpenFoodFacts returned HTTP {response.status_code}.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ExternalAPIError("OpenFoodFacts returned invalid JSON.") from exc

    return [normalize_product(raw) for raw in payload.get("products", [])]