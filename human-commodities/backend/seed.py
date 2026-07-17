"""Seed the catalog with a spread of human-needs commodities (domain-agnostic demo)."""
from db import init_db, get_conn

PRODUCTS = [
    # name, category, unit, description, cost, sell, stock
    ("Wheat Flour", "food", "kg", "Stone-ground whole wheat flour", 22, 38, 1200),
    ("Refined Sunflower Oil", "food", "litre", "Cold-pressed cooking oil", 95, 140, 600),
    ("Bath Soap Bar", "hygiene", "bar", "Herbal bath soap, 100g", 12, 25, 3000),
    ("Cotton Bedsheet", "textile", "piece", "Double-bed 100% cotton sheet", 210, 349, 400),
    ("Toothpaste", "hygiene", "tube", "Fluoride toothpaste, 150g", 28, 55, 1500),
    ("Table Salt", "food", "kg", "Iodised table salt", 8, 18, 2500),
    ("Hand Sanitizer", "hygiene", "bottle", "70% alcohol sanitizer, 200ml", 18, 40, 800),
    ("Rice (Sona Masuri)", "food", "kg", "Premium raw rice", 42, 62, 2000),
]


def seed():
    init_db()
    with get_conn() as conn:
        existing = conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
        if existing:
            print(f"Catalog already has {existing} products; skipping seed.")
            return
        conn.executemany(
            """INSERT INTO products (name, category, unit, description, cost_price, sell_price, stock_qty)
               VALUES (?,?,?,?,?,?,?)""",
            PRODUCTS,
        )
    print(f"Seeded {len(PRODUCTS)} products.")


if __name__ == "__main__":
    seed()
