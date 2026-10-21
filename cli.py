"""
Command-line interface for the inventory API.

Every command sends an HTTP request to the Flask API (which must be running)
and prints the result.

Usage examples:
    python cli.py list
    python cli.py list --search milk
    python cli.py view 1
    python cli.py add --name "Oat Milk" --brand Oatly --price 3.99 --stock 12
    python cli.py update 1 --price 5.49 --stock 30
    python cli.py delete 3
    python cli.py find --barcode 3017624010701
    python cli.py find --name "peanut butter"
    python cli.py import 737628064502 --price 2.75 --stock 15
    python cli.py enrich 4
    python cli.py            (no command -> interactive menu)

Set INVENTORY_API_URL to use a different server (default http://127.0.0.1:5000).
"""

import argparse
import os
import sys

import requests

API_URL = os.environ.get("INVENTORY_API_URL", "http://127.0.0.1:5000")
TIMEOUT = 15  # seconds; imports call OpenFoodFacts so allow some slack


class CLIError(Exception):
    """A problem worth showing to the user (bad input, API down, API error)."""


# --------------------------------------------------------------------------- #
# HTTP helper
# --------------------------------------------------------------------------- #
def api_request(method, path, **kwargs):
    """
    Call the inventory API and return the decoded JSON body.

    Raises CLIError with a readable message when the server is unreachable or
    answers with an error status.
    """
    url = f"{API_URL}{path}"
    try:
        response = requests.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.ConnectionError:
        raise CLIError(f"Cannot connect to the API at {API_URL}. Is the server running (python run.py)?")
    except requests.Timeout:
        raise CLIError("The API took too long to respond. Try again.")
    except requests.RequestException as exc:
        raise CLIError(f"Request failed: {exc}")

    try:
        body = response.json()
    except ValueError:
        body = None

    if not response.ok:
        message = body.get("error") if isinstance(body, dict) else None
        raise CLIError(message or f"API returned HTTP {response.status_code}.")
    return body


# --------------------------------------------------------------------------- #
# Input validation (used as argparse "type" functions)
# --------------------------------------------------------------------------- #
def positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"'{value}' is not a whole number")
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def non_negative_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"'{value}' is not a whole number")
    if number < 0:
        raise argparse.ArgumentTypeError("cannot be negative")
    return number


def non_negative_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"'{value}' is not a number")
    if number < 0:
        raise argparse.ArgumentTypeError("cannot be negative")
    return round(number, 2)


def barcode_type(value):
    value = str(value).strip()
    if not value.isdigit():
        raise argparse.ArgumentTypeError("barcode must contain digits only")
    return value


def non_empty(value):
    if not value:
        raise argparse.ArgumentTypeError("cannot be empty")
    return value


# --------------------------------------------------------------------------- #
# Output formatting
# --------------------------------------------------------------------------- #
def format_item_row(item):
    return (
        f"{item['id']:>4}  {item['product_name'][:30]:<30}  {item.get('brands', '')[:15]:<15}  "
        f"{'$' + format(item['price'], '.2f'):>9}  {item['stock']:>6}"
    )


def print_table(items):
    if not items:
        print("No items found.")
        return
    print(f"{'ID':>4}  {'Product':<30}  {'Brand':<15}  {'Price':>9}  {'Stock':>6}")
    print("-" * 72)
    for item in items:
        print(format_item_row(item))


def print_details(item):
    labels = [
        ("ID", "id"), ("Name", "product_name"), ("Brand", "brands"),
        ("Barcode", "barcode"), ("Quantity", "quantity"), ("Price", "price"),
        ("Stock", "stock"), ("Categories", "categories"),
        ("Nutri-Score", "nutriscore_grade"), ("Ingredients", "ingredients_text"),
    ]
    for label, key in labels:
        if key not in item:
            continue
        value = item[key]
        if key == "price":
            value = f"${value:.2f}"
        print(f"{label + ':':<13} {value if value not in ('', None) else '-'}")


# --------------------------------------------------------------------------- #
# Commands - each returns an exit code (0 = success)
# --------------------------------------------------------------------------- #
def cmd_list(args):
    params = {"search": args.search} if args.search else None
    print_table(api_request("GET", "/inventory", params=params))
    return 0


def cmd_view(args):
    print_details(api_request("GET", f"/inventory/{args.id}"))
    return 0


def cmd_add(args):
    payload = {"product_name": args.name, "price": args.price, "stock": args.stock}
    if args.brand:
        payload["brands"] = args.brand
    if args.barcode:
        payload["barcode"] = args.barcode
    item = api_request("POST", "/inventory", json=payload)
    print(f"Added item {item['id']}: {item['product_name']}")
    return 0


def cmd_update(args):
    payload = {}
    if args.price is not None:
        payload["price"] = args.price
    if args.stock is not None:
        payload["stock"] = args.stock
    if args.name:
        payload["product_name"] = args.name
    if not payload:
        raise CLIError("Nothing to update. Use --price, --stock and/or --name.")
    item = api_request("PATCH", f"/inventory/{args.id}", json=payload)
    print(f"Updated item {item['id']}: price ${item['price']:.2f}, stock {item['stock']}")
    return 0


def cmd_delete(args):
    if not args.yes:
        answer = input(f"Delete item {args.id}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 0
    api_request("DELETE", f"/inventory/{args.id}")
    print(f"Deleted item {args.id}.")
    return 0


def cmd_find(args):
    if args.barcode:
        print_details(api_request("GET", f"/external/barcode/{args.barcode}"))
        return 0
    products = api_request("GET", "/external/search", params={"name": args.name})
    if not products:
        print("No products found on OpenFoodFacts.")
        return 0
    for number, product in enumerate(products, start=1):
        print(f"{number}. {product['product_name'] or '(no name)'} "
              f"- {product['brands'] or 'unknown brand'} [barcode {product['barcode']}]")
    print("\nTip: add one with  python cli.py import <barcode> --price P --stock S")
    return 0


def cmd_import(args):
    payload = {"barcode": args.barcode, "price": args.price, "stock": args.stock}
    item = api_request("POST", "/inventory/import", json=payload)
    print(f"Imported from OpenFoodFacts as item {item['id']}:")
    print_details(item)
    return 0


def cmd_enrich(args):
    result = api_request("POST", f"/inventory/{args.id}/enrich")
    fields = result["updated_fields"]
    if fields:
        print(f"Item {args.id} updated with: {', '.join(fields)}")
    else:
        print(f"Item {args.id} already had all available details.")
    return 0


# --------------------------------------------------------------------------- #
# Interactive menu (runs when no command is given)
# --------------------------------------------------------------------------- #
MENU = """
==== Inventory Admin ====
1. List all items
2. View an item
3. Add an item
4. Update price / stock
5. Delete an item
6. Find a product on OpenFoodFacts
7. Import a product from OpenFoodFacts
0. Exit
"""


def prompt(text, parse=str, allow_blank=False):
    """Ask until the answer is valid; a blank answer returns None when allowed."""
    while True:
        raw = input(text).strip()
        if raw == "" and allow_blank:
            return None
        try:
            return parse(raw)
        except argparse.ArgumentTypeError as exc:
            print(f"  Invalid input: {exc}")
        except ValueError:
            print("  Invalid input, try again.")


def interactive_find():
    def one_or_two(value):
        if value not in ("1", "2"):
            raise argparse.ArgumentTypeError("enter 1 or 2")
        return value

    mode = prompt("Search by (1) barcode or (2) name? ", one_or_two)
    if mode == "1":
        return cmd_find(argparse.Namespace(barcode=prompt("Barcode: ", barcode_type), name=None))
    return cmd_find(argparse.Namespace(barcode=None, name=prompt("Name: ", non_empty)))


def interactive():
    actions = {
        "1": lambda: cmd_list(argparse.Namespace(search=None)),
        "2": lambda: cmd_view(argparse.Namespace(id=prompt("Item ID: ", positive_int))),
        "3": lambda: cmd_add(argparse.Namespace(
            name=prompt("Name: ", non_empty),
            brand=prompt("Brand (optional): ", allow_blank=True),
            barcode=prompt("Barcode (optional): ", barcode_type, allow_blank=True),
            price=prompt("Price: ", non_negative_float),
            stock=prompt("Stock: ", non_negative_int),
        )),
        "4": lambda: cmd_update(argparse.Namespace(
            id=prompt("Item ID: ", positive_int),
            price=prompt("New price (blank to keep): ", non_negative_float, allow_blank=True),
            stock=prompt("New stock (blank to keep): ", non_negative_int, allow_blank=True),
            name=None,
        )),
        "5": lambda: cmd_delete(argparse.Namespace(id=prompt("Item ID: ", positive_int), yes=False)),
        "6": interactive_find,
        "7": lambda: cmd_import(argparse.Namespace(
            barcode=prompt("Barcode: ", barcode_type),
            price=prompt("Price: ", non_negative_float),
            stock=prompt("Stock: ", non_negative_int),
        )),
    }
    while True:
        print(MENU)
        choice = input("Choose an option: ").strip()
        if choice == "0":
            print("Goodbye!")
            return 0
        action = actions.get(choice)
        if action is None:
            print("Unknown option.")
            continue
        try:
            action()
        except CLIError as exc:
            print(f"Error: {exc}")


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def build_parser():
    parser = argparse.ArgumentParser(
        prog="cli.py", description="Manage store inventory through the Flask API."
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("list", help="List inventory items")
    p.add_argument("--search", help="Filter by name or brand")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("view", help="Show one item")
    p.add_argument("id", type=positive_int)
    p.set_defaults(func=cmd_view)

    p = sub.add_parser("add", help="Add a new item")
    p.add_argument("--name", required=True)
    p.add_argument("--price", type=non_negative_float, required=True)
    p.add_argument("--stock", type=non_negative_int, required=True)
    p.add_argument("--brand")
    p.add_argument("--barcode", type=barcode_type)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("update", help="Update an item's price, stock or name")
    p.add_argument("id", type=positive_int)
    p.add_argument("--price", type=non_negative_float)
    p.add_argument("--stock", type=non_negative_int)
    p.add_argument("--name")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("delete", help="Delete an item")
    p.add_argument("id", type=positive_int)
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("find", help="Find a product on OpenFoodFacts")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--barcode", type=barcode_type)
    group.add_argument("--name")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("import", help="Add a product from OpenFoodFacts by barcode")
    p.add_argument("barcode", type=barcode_type)
    p.add_argument("--price", type=non_negative_float, default=0.0)
    p.add_argument("--stock", type=non_negative_int, default=0)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("enrich", help="Fill an item's details from OpenFoodFacts")
    p.add_argument("id", type=positive_int)
    p.set_defaults(func=cmd_enrich)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command is None:
            return interactive()
        return args.func(args)
    except CLIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())