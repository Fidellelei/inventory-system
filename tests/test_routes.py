"""
Tests for the Flask CRUD routes.

The inventory is reset before every test so tests can't affect each other.
Run with:  pytest -v
"""

import unittest

from app import create_app, data


class RouteTestCase(unittest.TestCase):
    def setUp(self):
        data.reset_inventory()
        self.client = create_app().test_client()


# ----------------------------------------------------------------- GET ---- #
class TestGetInventory(RouteTestCase):
    def test_list_returns_all_items(self):
        res = self.client.get("/inventory")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()), len(data.SEED_INVENTORY))

    def test_every_item_has_an_id(self):
        for item in self.client.get("/inventory").get_json():
            self.assertIn("id", item)

    def test_list_search_filters_by_name(self):
        res = self.client.get("/inventory?search=almond")
        names = [i["product_name"] for i in res.get_json()]
        self.assertEqual(names, ["Organic Almond Milk"])

    def test_list_search_filters_by_brand_case_insensitive(self):
        res = self.client.get("/inventory?search=FERRERO")
        self.assertEqual(len(res.get_json()), 1)

    def test_list_search_no_match_returns_empty_list(self):
        self.assertEqual(self.client.get("/inventory?search=zzz").get_json(), [])

    def test_get_single_item(self):
        res = self.client.get("/inventory/1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["product_name"], "Organic Almond Milk")

    def test_get_missing_item_returns_404(self):
        res = self.client.get("/inventory/999")
        self.assertEqual(res.status_code, 404)
        self.assertIn("error", res.get_json())

    def test_non_integer_id_returns_json_404(self):
        res = self.client.get("/inventory/abc")
        self.assertEqual(res.status_code, 404)
        self.assertIn("error", res.get_json())


# ---------------------------------------------------------------- POST ---- #
class TestCreateItem(RouteTestCase):
    def test_create_item(self):
        res = self.client.post("/inventory", json={
            "product_name": "Oat Milk", "brands": "Oatly", "price": 3.99, "stock": 12,
        })
        self.assertEqual(res.status_code, 201)
        item = res.get_json()
        self.assertEqual(item["id"], 4)
        self.assertEqual(item["price"], 3.99)
        self.assertEqual(len(data.inventory), 4)

    def test_create_fills_defaults(self):
        item = self.client.post("/inventory", json={"product_name": "Bread"}).get_json()
        self.assertEqual(item["stock"], 0)
        self.assertEqual(item["price"], 0.0)
        self.assertEqual(item["brands"], "")

    def test_create_requires_name(self):
        res = self.client.post("/inventory", json={"price": 1})
        self.assertEqual(res.status_code, 400)

    def test_create_rejects_non_json(self):
        res = self.client.post("/inventory", data="not json", content_type="text/plain")
        self.assertEqual(res.status_code, 400)

    def test_create_rejects_negative_price(self):
        res = self.client.post("/inventory", json={"product_name": "X", "price": -1})
        self.assertEqual(res.status_code, 400)

    def test_create_rejects_bad_stock(self):
        for bad in ("lots", -5, 2.5, True):
            res = self.client.post("/inventory", json={"product_name": "X", "stock": bad})
            self.assertEqual(res.status_code, 400, bad)

    def test_create_rejects_unknown_fields(self):
        res = self.client.post("/inventory", json={"product_name": "X", "colour": "red"})
        self.assertEqual(res.status_code, 400)

    def test_create_rejects_duplicate_barcode(self):
        res = self.client.post("/inventory", json={
            "product_name": "Dup", "barcode": "3017624010701",
        })
        self.assertEqual(res.status_code, 409)


# --------------------------------------------------------------- PATCH ---- #
class TestUpdateItem(RouteTestCase):
    def test_update_price_and_stock(self):
        res = self.client.patch("/inventory/1", json={"price": 5.49, "stock": 30})
        self.assertEqual(res.status_code, 200)
        item = res.get_json()
        self.assertEqual((item["price"], item["stock"]), (5.49, 30))
        self.assertEqual(data.find_item(1)["stock"], 30)

    def test_update_leaves_other_fields(self):
        self.client.patch("/inventory/1", json={"stock": 1})
        self.assertEqual(data.find_item(1)["product_name"], "Organic Almond Milk")

    def test_update_cannot_change_id(self):
        res = self.client.patch("/inventory/1", json={"id": 50})
        self.assertEqual(res.status_code, 400)

    def test_update_missing_item(self):
        self.assertEqual(self.client.patch("/inventory/999", json={"stock": 1}).status_code, 404)

    def test_update_empty_body(self):
        self.assertEqual(self.client.patch("/inventory/1", json={}).status_code, 400)

    def test_update_rejects_invalid_price(self):
        self.assertEqual(self.client.patch("/inventory/1", json={"price": "cheap"}).status_code, 400)


# -------------------------------------------------------------- DELETE ---- #
class TestDeleteItem(RouteTestCase):
    def test_delete_item(self):
        res = self.client.delete("/inventory/2")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(data.find_item(2))
        self.assertEqual(self.client.get("/inventory/2").status_code, 404)

    def test_delete_missing_item(self):
        self.assertEqual(self.client.delete("/inventory/999").status_code, 404)

    def test_wrong_method_returns_405(self):
        self.assertEqual(self.client.put("/inventory/1", json={}).status_code, 405)

    def test_health(self):
        res = self.client.get("/health")
        self.assertEqual(res.get_json(), {"status": "ok", "items": 3})