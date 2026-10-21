"""
Tests for the OpenFoodFacts client.

`requests.get` is replaced with a mock, so no real network calls happen.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from app.external_api import (
    ExternalAPIError,
    fetch_product_by_barcode,
    normalize_product,
    search_products_by_name,
)


def fake_response(status_code=200, payload=None, bad_json=False):
    """Build a fake requests.Response."""
    response = MagicMock()
    response.status_code = status_code
    if bad_json:
        response.json.side_effect = ValueError("no json")
    else:
        response.json.return_value = payload
    return response


RAW_PRODUCT = {
    "code": "3017624010701",
    "product_name": "Nutella",
    "brands": "Ferrero",
    "ingredients_text": "Sugar, palm oil, hazelnuts",
    "categories": "Spreads",
    "quantity": "400 g",
    "nutriscore_grade": "e",
    "image_url": "https://images.openfoodfacts.org/x.jpg",
    "nutriments": {"energy": 2252},  # extra field that should be dropped
}


class TestNormalizeProduct(unittest.TestCase):
    def test_keeps_only_known_fields(self):
        product = normalize_product(RAW_PRODUCT)
        self.assertNotIn("nutriments", product)
        self.assertEqual(product["barcode"], "3017624010701")
        self.assertEqual(product["brands"], "Ferrero")

    def test_missing_fields_become_empty_strings(self):
        product = normalize_product({"code": "1"})
        self.assertEqual(product["product_name"], "")


class TestFetchByBarcode(unittest.TestCase):
    @patch("app.external_api.requests.get")
    def test_success(self, mock_get):
        mock_get.return_value = fake_response(200, {"status": 1, "product": RAW_PRODUCT})
        product = fetch_product_by_barcode("3017624010701")

        self.assertEqual(product["product_name"], "Nutella")
        url = mock_get.call_args.args[0]
        self.assertTrue(url.endswith("/api/v2/product/3017624010701.json"))
        self.assertIn("User-Agent", mock_get.call_args.kwargs["headers"])

    @patch("app.external_api.requests.get")
    def test_unknown_barcode_404_returns_none(self, mock_get):
        mock_get.return_value = fake_response(404, {"status": 0})
        self.assertIsNone(fetch_product_by_barcode("0000000000000"))

    @patch("app.external_api.requests.get")
    def test_status_zero_returns_none(self, mock_get):
        mock_get.return_value = fake_response(200, {"status": 0})
        self.assertIsNone(fetch_product_by_barcode("123"))

    @patch("app.external_api.requests.get")
    def test_server_error_raises(self, mock_get):
        mock_get.return_value = fake_response(503)
        with self.assertRaises(ExternalAPIError):
            fetch_product_by_barcode("123")

    @patch("app.external_api.requests.get", side_effect=requests.ConnectionError("offline"))
    def test_network_failure_raises(self, _):
        with self.assertRaises(ExternalAPIError):
            fetch_product_by_barcode("123")

    @patch("app.external_api.requests.get", side_effect=requests.Timeout())
    def test_timeout_raises(self, _):
        with self.assertRaises(ExternalAPIError):
            fetch_product_by_barcode("123")

    @patch("app.external_api.requests.get")
    def test_invalid_json_raises(self, mock_get):
        mock_get.return_value = fake_response(200, bad_json=True)
        with self.assertRaises(ExternalAPIError):
            fetch_product_by_barcode("123")

    @patch("app.external_api.requests.get")
    def test_non_digit_barcode_rejected_without_request(self, mock_get):
        with self.assertRaises(ValueError):
            fetch_product_by_barcode("abc123")
        mock_get.assert_not_called()


class TestSearchByName(unittest.TestCase):
    @patch("app.external_api.requests.get")
    def test_success(self, mock_get):
        mock_get.return_value = fake_response(200, {"products": [RAW_PRODUCT, {"code": "2"}]})
        products = search_products_by_name("nutella")

        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["product_name"], "Nutella")
        self.assertEqual(mock_get.call_args.kwargs["params"]["search_terms"], "nutella")

    @patch("app.external_api.requests.get")
    def test_no_results(self, mock_get):
        mock_get.return_value = fake_response(200, {"products": []})
        self.assertEqual(search_products_by_name("zzzz"), [])

    @patch("app.external_api.requests.get")
    def test_blank_name_rejected(self, mock_get):
        with self.assertRaises(ValueError):
            search_products_by_name("   ")
        mock_get.assert_not_called()

    @patch("app.external_api.requests.get")
    def test_server_error_raises(self, mock_get):
        mock_get.return_value = fake_response(500)
        with self.assertRaises(ExternalAPIError):
            search_products_by_name("milk")

    @patch("app.external_api.requests.get", side_effect=requests.ConnectionError())
    def test_network_failure_raises(self, _):
        with self.assertRaises(ExternalAPIError):
            search_products_by_name("milk")