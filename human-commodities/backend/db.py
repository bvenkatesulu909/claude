"""SQLite storage layer for the Human Commodities platform.

Data-driven / domain-agnostic: the product catalog defines the domain, so the
same schema works for food, hygiene goods, textiles, raw staples, etc.
"""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get(
    "HC_DB_PATH", os.path.join(os.path.dirname(__file__), "commodities.db")
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    category     TEXT    NOT NULL DEFAULT 'general',
    unit         TEXT    NOT NULL DEFAULT 'unit',
    description  TEXT    NOT NULL DEFAULT '',
    cost_price   REAL    NOT NULL DEFAULT 0,
    sell_price   REAL    NOT NULL DEFAULT 0,
    stock_qty    REAL    NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS production_plans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   INTEGER REFERENCES products(id) ON DELETE CASCADE,
    quantity     REAL    NOT NULL DEFAULT 0,
    status       TEXT    NOT NULL DEFAULT 'draft',
    plan_json    TEXT    NOT NULL DEFAULT '{}',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS research_reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    topic        TEXT    NOT NULL,
    content      TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER REFERENCES products(id) ON DELETE SET NULL,
    quantity      REAL    NOT NULL DEFAULT 0,
    customer_name TEXT    NOT NULL DEFAULT 'walk-in',
    total         REAL    NOT NULL DEFAULT 0,
    status        TEXT    NOT NULL DEFAULT 'placed',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL DEFAULT 'sale',   -- sale | purchase | expense
    amount      REAL    NOT NULL DEFAULT 0,
    description TEXT    NOT NULL DEFAULT '',
    ref_id      INTEGER,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent      TEXT    NOT NULL,
    input      TEXT    NOT NULL DEFAULT '',
    output     TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL DEFAULT 'ok',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"Initialised database at {DB_PATH}")
