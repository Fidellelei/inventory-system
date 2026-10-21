"""
Simulated data storage.

The inventory lives in a plain Python list (the "database array"). Each item
mirrors the shape of an OpenFoodFacts product record, plus the fields a
retailer needs: an `id`, a `price` and a `stock` level.
"""

import copy

# Seed data, modelled on real OpenFoodFacts products.
SEED_INVENTORY = [
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
        "stock": 25,
    },
    {
        "id": 2,
        "barcode": "3017624010701",
        "product_name": "Nutella",
        "brands": "Ferrero",
        "ingredients_text": "Sugar, palm oil, hazelnuts, skimmed milk powder, fat-reduced cocoa",
        "categories": "Spreads, Sweet spreads, Hazelnut spreads",
        "quantity": "400 g",
        "nutriscore_grade": "e",
        "image_url": "",
        "price": 6.50,
        "stock": 40,
    },
    {
        "id": 3,
        "barcode": "5449000000996",
        "product_name": "Coca-Cola Original Taste",
        "brands": "Coca-Cola",
        "ingredients_text": "Carbonated water, sugar, colour (caramel E150d), phosphoric acid, natural flavourings, caffeine",
        "categories": "Beverages, Carbonated drinks, Sodas",
        "quantity": "330 ml",
        "nutriscore_grade": "e",
        "image_url": "",
        "price": 1.25,
        "stock": 120,
    },
]

# The live "database" the API reads and writes.
inventory = copy.deepcopy(SEED_INVENTORY)


def reset_inventory():
    """Restore the inventory to its seed state (used by the tests)."""
    inventory.clear()
    inventory.extend(copy.deepcopy(SEED_INVENTORY))


def next_id():
    """Return the next free integer id."""
    return max((item["id"] for item in inventory), default=0) + 1


def find_item(item_id):
    """Return the item with this id, or None."""
    return next((item for item in inventory if item["id"] == item_id), None)