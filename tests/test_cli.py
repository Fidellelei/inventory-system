"""
Tests for the CLI.

Two styles are used:
  * Unit tests mock `requests.request` and check what the CLI sends and prints.
  * End-to-end tests route the CLI's HTTP calls into the Flask test client,
    so a CLI command really changes the inventory array.
"""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

import requests

import cli
from app import create_app, data


def fake_response(status_code=200, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json.return_value = payload
    return response


def run_cli(argv):
    """Run the CLI and return (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


ITEM = {
    "id": 1, "barcode": "123", "product_name": "Organic Almond Milk", "brands": "Silk",
    "ingredients_text": "", "categories": "", "quantity": "", "nutriscore_grade": "",
    "image_url": "", "price": 4.99, "stock": 25,
}


# ------------------------------------------------- mocked HTTP unit tests --- #
class TestCLICommands(unittest.TestCase):
    @patch("cli.requests.request")
    def test_list(self, mock_request):
        mock_request.return_value = fake_response(200, [ITEM])
        code, out, _ = run_cli(["list"])
        self.assertEqual(code, 0)
        self.assertIn("Organic Almond Milk", out)
        method, url = mock_request.call_args.args
        self.assertEqual((method, url), ("GET", f"{cli.API_URL}/inventory"))

    @patch("cli.requests.request")
    def test_list_with_search(self, mock_request):
        mock_request.return_value = fake_response(200, [])
        code, out, _ = run_cli(["list", "--search", "milk"])
        self.assertEqual(mock_request.call_args.kwargs["params"], {"search": "milk"})
        self.assertIn("No items found", out)

    @patch("cli.requests.request")
    def test_view(self, mock_request):
        mock_request.return_value = fake_response(200, ITEM)
        code, out, _ = run_cli(["view", "1"])
        self.assertEqual(code, 0)
        self.assertIn("$4.99", out)

    @patch("cli.requests.request")
    def test_view_missing_item_shows_api_error(self, mock_request):
        mock_request.return_value = fake_response(404, {"error": "Item 9 not found."})
        code, _, err = run_cli(["view", "9"])
        self.assertEqual(code, 1)
        self.assertIn("Item 9 not found.", err)

    @patch("cli.requests.request")
    def test_add_sends_payload(self, mock_request):
        mock_request.return_value = fake_response(201, dict(ITEM, id=4, product_name="Oat Milk"))
        code, out, _ = run_cli(["add", "--name", "Oat Milk", "--price", "3.99",
                                "--stock", "12", "--brand", "Oatly"])
        self.assertEqual(code, 0)
        self.assertEqual(mock_request.call_args.kwargs["json"], {
            "product_name": "Oat Milk", "price": 3.99, "stock": 12, "brands": "Oatly",
        })
        self.assertIn("Added item 4", out)

    @patch("cli.requests.request")
    def test_update_price_and_stock(self, mock_request):
        mock_request.return_value = fake_response(200, dict(ITEM, price=5.49, stock=30))
        code, out, _ = run_cli(["update", "1", "--price", "5.49", "--stock", "30"])
        self.assertEqual(code, 0)
        self.assertEqual(mock_request.call_args.args[0], "PATCH")
        self.assertEqual(mock_request.call_args.kwargs["json"], {"price": 5.49, "stock": 30})

    @patch("cli.requests.request")
    def test_update_with_nothing_to_change(self, mock_request):
        code, _, err = run_cli(["update", "1"])
        self.assertEqual(code, 1)
        self.assertIn("Nothing to update", err)
        mock_request.assert_not_called()

    @patch("cli.requests.request")
    def test_delete_with_yes_flag(self, mock_request):
        mock_request.return_value = fake_response(200, {"message": "Item 1 deleted."})
        code, out, _ = run_cli(["delete", "1", "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(mock_request.call_args.args[0], "DELETE")
        self.assertIn("Deleted item 1", out)

    @patch("builtins.input", return_value="n")
    @patch("cli.requests.request")
    def test_delete_cancelled_at_prompt(self, mock_request, _):
        code, out, _ = run_cli(["delete", "1"])
        self.assertIn("Cancelled", out)
        mock_request.assert_not_called()

    @patch("cli.requests.request")
    def test_find_by_barcode(self, mock_request):
        mock_request.return_value = fake_response(200, dict(ITEM, product_name="Nutella"))
        code, out, _ = run_cli(["find", "--barcode", "3017624010701"])
        self.assertIn("Nutella", out)
        self.assertTrue(mock_request.call_args.args[1].endswith("/external/barcode/3017624010701"))

    @patch("cli.requests.request")
    def test_find_by_name_lists_results(self, mock_request):
        mock_request.return_value = fake_response(200, [
            {"product_name": "Peanut Butter", "brands": "Skippy", "barcode": "111"},
        ])
        code, out, _ = run_cli(["find", "--name", "peanut butter"])
        self.assertIn("1. Peanut Butter - Skippy [barcode 111]", out)

    @patch("cli.requests.request")
    def test_find_reports_external_api_failure(self, mock_request):
        mock_request.return_value = fake_response(502, {"error": "OpenFoodFacts returned HTTP 503."})
        code, _, err = run_cli(["find", "--name", "milk"])
        self.assertEqual(code, 1)
        self.assertIn("HTTP 503", err)

    @patch("cli.requests.request")
    def test_import(self, mock_request):
        mock_request.return_value = fake_response(201, dict(ITEM, id=4))
        code, out, _ = run_cli(["import", "737628064502", "--price", "2.75", "--stock", "15"])
        self.assertEqual(mock_request.call_args.kwargs["json"],
                         {"barcode": "737628064502", "price": 2.75, "stock": 15})
        self.assertIn("item 4", out)

    @patch("cli.requests.request")
    def test_enrich(self, mock_request):
        mock_request.return_value = fake_response(200, {"item": ITEM, "updated_fields": ["brands"]})
        code, out, _ = run_cli(["enrich", "1"])
        self.assertIn("updated with: brands", out)


# --------------------------------------------------------- error handling --- #
class TestCLIErrors(unittest.TestCase):
    @patch("cli.requests.request", side_effect=requests.ConnectionError())
    def test_server_down(self, _):
        code, _, err = run_cli(["list"])
        self.assertEqual(code, 1)
        self.assertIn("Cannot connect", err)

    @patch("cli.requests.request", side_effect=requests.Timeout())
    def test_timeout(self, _):
        code, _, err = run_cli(["list"])
        self.assertIn("too long", err)

    def assert_rejected(self, argv):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            cli.main(argv)
        self.assertEqual(ctx.exception.code, 2)  # argparse usage error

    def test_invalid_inputs_rejected_before_any_request(self):
        with patch("cli.requests.request") as mock_request:
            self.assert_rejected(["view", "abc"])
            self.assert_rejected(["view", "0"])
            self.assert_rejected(["add", "--name", "X", "--price", "-1", "--stock", "1"])
            self.assert_rejected(["add", "--name", "X", "--price", "1", "--stock", "many"])
            self.assert_rejected(["update", "1", "--stock", "-3"])
            self.assert_rejected(["find", "--barcode", "12ab"])
            self.assert_rejected(["find"])  # needs --barcode or --name
            mock_request.assert_not_called()


# --------------------------------------------------------- interactive menu --- #
class TestInteractiveMenu(unittest.TestCase):
    @patch("cli.requests.request")
    def test_menu_list_then_exit(self, mock_request):
        mock_request.return_value = fake_response(200, [ITEM])
        with patch("builtins.input", side_effect=["1", "0"]):
            code, out, _ = run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("Organic Almond Milk", out)
        self.assertIn("Goodbye", out)

    @patch("cli.requests.request")
    def test_menu_reprompts_on_invalid_input(self, mock_request):
        mock_request.return_value = fake_response(200, ITEM)
        # unknown option "9", view (2), bad id "x", valid id "1", exit
        with patch("builtins.input", side_effect=["9", "2", "x", "1", "0"]):
            code, out, _ = run_cli([])
        self.assertIn("Unknown option", out)
        self.assertIn("Invalid input", out)

    @patch("cli.requests.request", side_effect=requests.ConnectionError())
    def test_menu_survives_api_errors(self, _):
        with patch("builtins.input", side_effect=["1", "0"]):
            code, out, _ = run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("Error: Cannot connect", out)


# ------------------------------------------- end-to-end through Flask ------ #
class TestCLIAgainstFlaskApp(unittest.TestCase):
    """The CLI talks to the real Flask app (in-process) instead of a mock."""

    def setUp(self):
        data.reset_inventory()
        self.client = create_app().test_client()
        patcher = patch("cli.requests.request", side_effect=self.forward)
        patcher.start()
        self.addCleanup(patcher.stop)

    def forward(self, method, url, timeout=None, params=None, json=None):
        path = url.replace(cli.API_URL, "")
        res = self.client.open(path, method=method, query_string=params, json=json)
        return fake_response(res.status_code, res.get_json())

    def test_add_update_delete_cycle(self):
        run_cli(["add", "--name", "Oat Milk", "--price", "3.99", "--stock", "12"])
        self.assertEqual(data.find_item(4)["product_name"], "Oat Milk")

        run_cli(["update", "4", "--stock", "50"])
        self.assertEqual(data.find_item(4)["stock"], 50)

        run_cli(["delete", "4", "-y"])
        self.assertIsNone(data.find_item(4))

    @patch("app.routes.fetch_product_by_barcode")
    def test_import_from_openfoodfacts_adds_to_array(self, mock_fetch):
        mock_fetch.return_value = {
            "barcode": "737628064502", "product_name": "Thai Peanut Noodle Kit",
            "brands": "Simply Asia", "ingredients_text": "", "categories": "",
            "quantity": "", "nutriscore_grade": "", "image_url": "",
        }
        code, out, _ = run_cli(["import", "737628064502", "--price", "2.75", "--stock", "15"])
        self.assertEqual(code, 0)
        self.assertEqual(data.find_item(4)["brands"], "Simply Asia")