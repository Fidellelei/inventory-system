# Inventory Management System — Flask REST API

An administrator portal backend for a small retail store. Employees can add, view,
update and delete inventory items through a Flask REST API, look products up on
[OpenFoodFacts](https://openfoodfacts.github.io/openfoodfacts-server/api/) by
barcode or name, import those products straight into the inventory, and do all of
it from a command-line interface.

Storage is simulated with an in-memory Python list (`app/data.py`), so data resets
whenever the server restarts.

---

## Project structure

```
inventory-system/
├── app/
│   ├── __init__.py        # create_app() factory, JSON error handlers
│   ├── data.py            # mock database array (seed data + helpers)
│   ├── external_api.py    # OpenFoodFacts client (barcode lookup + name search)
│   └── routes.py          # CRUD routes + OpenFoodFacts helper routes
├── tests/
│   ├── test_routes.py          # CRUD endpoint tests
│   ├── test_external_routes.py # OpenFoodFacts helper route tests
│   ├── test_external_api.py    # OpenFoodFacts client tests (mocked requests)
│   └── test_cli.py             # CLI tests (mocked HTTP + end-to-end via Flask)
├── cli.py                 # command-line interface
├── run.py                 # starts the API in debug mode
├── requirements.txt
└── pytest.ini
```

---

## Installation and setup

Requires Python 3.9+.

```bash
git clone https://github.com/Fidellelei/inventory-system.git
cd inventory-system

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Start the API (Flask debug mode, http://127.0.0.1:5000):

```bash
python run.py
```

In a second terminal (with the venv activated), use the CLI:

```bash
python cli.py --help
```

To point the CLI at another server, set `INVENTORY_API_URL`
(e.g. `export INVENTORY_API_URL=http://127.0.0.1:8000`). The server port can be
changed with the `PORT` environment variable.

---

## Data model

Each item follows the shape of an OpenFoodFacts product, plus an `id`, `price`
and `stock`:

```json
{
  "id": 1,
  "barcode": "0025293600232",
  "product_name": "Organic Almond Milk",
  "brands": "Silk",
  "ingredients_text": "Filtered water, almonds, cane sugar, sea salt, locust bean gum",
  "categories": "Plant-based foods, Beverages, Almond milks",
  "quantity": "1.89 l",
  "nutriscore_grade": "b",
  "image_url": "",
  "price": 4.99,
  "stock": 25
}
```

Rules: `product_name` is required on create; `price` must be a number ≥ 0;
`stock` must be a whole number ≥ 0; `id` is assigned by the server and cannot be
changed; barcodes must be unique.

---

## API endpoints

All responses are JSON. Errors look like `{"error": "message"}`.

### CRUD

| Method | Route | Body | Success | Errors |
|---|---|---|---|---|
| GET | `/inventory` | — (optional `?search=text` filters by name/brand) | 200, list of items | — |
| GET | `/inventory/<id>` | — | 200, item | 404 |
| POST | `/inventory` | `product_name` (required), `price`, `stock`, `brands`, `barcode`, … | 201, new item | 400 invalid, 409 duplicate barcode |
| PATCH | `/inventory/<id>` | any subset of item fields, e.g. `{"price": 5.49, "stock": 30}` | 200, updated item | 400, 404 |
| DELETE | `/inventory/<id>` | — | 200, `{"message", "item"}` | 404 |

### OpenFoodFacts helper routes

| Method | Route | Body | What it does |
|---|---|---|---|
| GET | `/external/barcode/<barcode>` | — | Looks a product up on OpenFoodFacts (not saved). 404 if unknown, 502 if OpenFoodFacts is unreachable. |
| GET | `/external/search?name=<text>` | — | Searches OpenFoodFacts by name, returns up to 5 products (not saved). |
| POST | `/inventory/import` | `{"barcode": "...", "price": 2.75, "stock": 15}` | Fetches the product by barcode and **adds it to the inventory array**. 201 on success. |
| POST | `/inventory/<id>/enrich` | — | Fills an existing item's empty fields (brand, ingredients, …) from OpenFoodFacts using its barcode. Never changes price or stock. |
| GET | `/health` | — | `{"status": "ok", "items": n}` |

**Search fallback:** name search uses OpenFoodFacts' classic full-text search
(`/cgi/search.pl`). That service is often overloaded (HTTP 503) or rate limited,
so if it fails the client automatically retries with OpenFoodFacts' newer search
service (`search.openfoodfacts.org`). An error is returned only if both fail.

### Example requests (curl / Postman)

```bash
curl http://127.0.0.1:5000/inventory
curl http://127.0.0.1:5000/inventory/1

curl -X POST http://127.0.0.1:5000/inventory \
     -H "Content-Type: application/json" \
     -d '{"product_name": "Oat Milk", "brands": "Oatly", "price": 3.99, "stock": 12}'

curl -X PATCH http://127.0.0.1:5000/inventory/1 \
     -H "Content-Type: application/json" \
     -d '{"price": 5.49, "stock": 30}'

curl -X DELETE http://127.0.0.1:5000/inventory/3

curl http://127.0.0.1:5000/external/barcode/3017624010701
curl "http://127.0.0.1:5000/external/search?name=peanut%20butter"

curl -X POST http://127.0.0.1:5000/inventory/import \
     -H "Content-Type: application/json" \
     -d '{"barcode": "4056489424925", "price": 3.50, "stock": 20}'
```

---

## CLI usage

The API server must be running (`python run.py`).

| Task | Command |
|---|---|
| List all items | `python cli.py list` |
| Search the inventory | `python cli.py list --search milk` |
| View one item | `python cli.py view 1` |
| Add an item | `python cli.py add --name "Oat Milk" --brand Oatly --price 3.99 --stock 12` |
| Update price / stock | `python cli.py update 1 --price 5.49 --stock 30` |
| Delete an item | `python cli.py delete 3` (asks to confirm; add `-y` to skip) |
| Find on OpenFoodFacts by barcode | `python cli.py find --barcode 3017624010701` |
| Find on OpenFoodFacts by name | `python cli.py find --name "peanut butter"` |
| Import from OpenFoodFacts | `python cli.py import 4056489424925 --price 3.50 --stock 20` |
| Fill in details for an item | `python cli.py enrich 4` |
| Interactive menu | `python cli.py` (no command) |

Example session:

```
$ python cli.py list
  ID  Product                         Brand                Price   Stock
------------------------------------------------------------------------
   1  Organic Almond Milk             Silk                 $4.99      25
   2  Nutella                         Ferrero              $6.50      40
   3  Coca-Cola Original Taste        Coca-Cola            $1.25     120

$ python cli.py find --name "peanut butter"
1. Be Nuts ! - Pâte à tartiner Cacahuète - Andros [barcode 3608580124047]
2. Menguy's Beurre de cacahuètes creamy - Menguy's [barcode 3327272107259]
...

$ python cli.py update 4 --stock -3
cli.py update: error: argument --stock: cannot be negative

$ python cli.py view 99
Error: Item 99 not found.
```

### Error handling

- Invalid input (non-numeric IDs, negative price/stock, non-digit barcodes) is
  rejected by the CLI before any request is sent; the interactive menu re-prompts.
- If the API server is down the CLI prints
  `Cannot connect to the API at http://127.0.0.1:5000. Is the server running?`
- API errors (404, 400, 409) are shown as `Error: <message>` with exit code 1.
- If OpenFoodFacts is unreachable or times out, the API answers 502 and the CLI
  shows the reason; nothing is added to the inventory.

---

## Testing

```bash
pytest -v
```

82 tests cover every feature. No test touches the network: `unittest.mock`
replaces `requests` (or the OpenFoodFacts client functions) with fake responses.

| File | Covers |
|---|---|
| `tests/test_routes.py` | GET / POST / PATCH / DELETE, validation, search filter, 404/405 handling |
| `tests/test_external_routes.py` | OpenFoodFacts helper routes: lookup, search, import, enrich, upstream failures |
| `tests/test_external_api.py` | OpenFoodFacts client: success, unknown barcode, server errors, timeouts, connection errors, invalid JSON, input validation, field normalisation, search fallback |
| `tests/test_cli.py` | Every CLI command, argument validation, server-down / timeout handling, the interactive menu, and end-to-end runs where the CLI drives the real Flask app |

### Debugging

`run.py` starts Flask with `debug=True` (auto-reload and in-browser tracebacks).
The curl examples above can be imported into Postman to exercise each endpoint.

---

## Git workflow

Each feature was built on its own branch and merged into `main` through a pull
request, after which the branch was deleted:

| Branch | Feature |
|---|---|
| `feature/crud-api` | Flask app, mock database, CRUD routes + tests |
| `feature/openfoodfacts` | OpenFoodFacts client, helper routes + tests |
| `feature/cli` | Command-line interface + tests |
| `fix/search-fallback` | Fallback to the newer OpenFoodFacts search when classic search fails |
| `docs/readme` | README and documentation |