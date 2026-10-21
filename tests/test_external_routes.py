"""
Tests for the OpenFoodFacts helper routes.

The client functions are patched where routes.py uses them, so OpenFoodFacts
is never actually called.
"""

import unittest
from unittest.mock import patch

from app import create_app, data
from app.external_api import ExternalAPIError

SAMPLE_PRODUCT = {
    "barcode": "737628064502",
    "product_name": "Thai Peanut Noodle Kit",
    "brands": "Simply Asia",
    "ingredients_text": "Rice noodles, peanut sauce",
    "categories": "Noodles",
    "quantity": "155 g",
    "nutriscore_grade": "d",
    "image_url": "https://example.com/img.jpg",
}


class TestExternalRoutes(unittest.TestCase):
    def setUp(self):
        data.reset_inventory()
        self.client = create_app().test_client()

    # ---- lookup by barcode ----
    @patch("app.routes.fetch_product_by_barcode", return_value=SAMPLE_PRODUCT)
    def test_lookup_by_barcode(self, mock_fetch):
        res = self.client.get("/external/barcode/737628064502")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["product_name"], "Thai Peanut Noodle Kit")
        mock_fetch.assert_called_once_with("737628064502")

    @patch("app.routes.fetch_product_by_barcode", return_value=None)
    def test_lookup_unknown_barcode(self, _):
        self.assertEqual(self.client.get("/external/barcode/000").status_code, 404)

    @patch("app.routes.fetch_product_by_barcode", side_effect=ValueError("Barcode must contain digits only."))
    def test_lookup_invalid_barcode(self, _):
        self.assertEqual(self.client.get("/external/barcode/abc").status_code, 400)

    @patch("app.routes.fetch_product_by_barcode", side_effect=ExternalAPIError("down"))
    def test_lookup_upstream_failure_returns_502(self, _):
        res = self.client.get("/external/barcode/123")
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.get_json()["error"], "down")

    # ---- search by name ----
    @patch("app.routes.search_products_by_name", return_value=[SAMPLE_PRODUCT])
    def test_search_by_name(self, mock_search):
        res = self.client.get("/external/search?name=noodle")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()), 1)
        mock_search.assert_called_once_with("noodle")

    @patch("app.routes.search_products_by_name", side_effect=ValueError("A product name is required for searching."))
    def test_search_requires_name(self, _):
        self.assertEqual(self.client.get("/external/search").status_code, 400)

    @patch("app.routes.search_products_by_name", side_effect=ExternalAPIError("down"))
    def test_search_upstream_failure(self, _):
        self.assertEqual(self.client.get("/external/search?name=x").status_code, 502)

    # ---- import into inventory ----
    @patch("app.routes.fetch_product_by_barcode", return_value=dict(SAMPLE_PRODUCT))
    def test_import_adds_product_to_inventory(self, _):
        res = self.client.post("/inventory/import", json={
            "barcode": "737628064502", "price": 2.75, "stock": 15,
        })
        self.assertEqual(res.status_code, 201)
        item = res.get_json()
        self.assertEqual(item["id"], 4)
        self.assertEqual(item["product_name"], "Thai Peanut Noodle Kit")
        self.assertEqual((item["price"], item["stock"]), (2.75, 15))
        self.assertIn(item, data.inventory)

    def test_import_requires_barcode(self):
        self.assertEqual(self.client.post("/inventory/import", json={}).status_code, 400)

    def test_import_rejects_existing_barcode(self):
        res = self.client.post("/inventory/import", json={"barcode": "3017624010701"})
        self.assertEqual(res.status_code, 409)

    def test_import_rejects_bad_price(self):
        res = self.client.post("/inventory/import", json={"barcode": "1", "price": -2})
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.fetch_product_by_barcode", return_value=None)
    def test_import_unknown_barcode(self, _):
        res = self.client.post("/inventory/import", json={"barcode": "000"})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(len(data.inventory), 3)

    @patch("app.routes.fetch_product_by_barcode", side_effect=ExternalAPIError("down"))
    def test_import_upstream_failure_adds_nothing(self, _):
        res = self.client.post("/inventory/import", json={"barcode": "123"})
        self.assertEqual(res.status_code, 502)
        self.assertEqual(len(data.inventory), 3)

    # ---- enrich an existing item ----
    @patch("app.routes.fetch_product_by_barcode")
    def test_enrich_fills_only_empty_fields(self, mock_fetch):
        created = self.client.post("/inventory", json={
            "product_name": "My Noodles", "barcode": "737628064502", "price": 2, "stock": 5,
        }).get_json()
        mock_fetch.return_value = dict(SAMPLE_PRODUCT)

        res = self.client.post(f"/inventory/{created['id']}/enrich")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["item"]["product_name"], "My Noodles")  # kept
        self.assertEqual(body["item"]["brands"], "Simply Asia")      # filled
        self.assertEqual(body["item"]["price"], 2)                   # untouched
        self.assertIn("brands", body["updated_fields"])

    def test_enrich_requires_barcode(self):
        item = self.client.post("/inventory", json={"product_name": "Loose apples"}).get_json()
        self.assertEqual(self.client.post(f"/inventory/{item['id']}/enrich").status_code, 400)

    def test_enrich_missing_item(self):
        self.assertEqual(self.client.post("/inventory/999/enrich").status_code, 404)