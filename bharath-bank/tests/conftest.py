"""Shared pytest fixtures for the Bharath Bank test suite.

The application under test keeps its SQLite path in a single module-level
global, ``app.DB_FILE``, and both ``get_db()`` and ``init_db()`` read that
global at call time rather than caching it anywhere. That means tests can get
a fully isolated, throwaway database simply by monkeypatching ``app.DB_FILE``
to point at a per-test temp file *before* calling ``app.init_db()`` -- no
changes to app.py/finance.py are required.
"""
import os
import sqlite3
import sys

import pytest

# Make the project root (one level up from this tests/ directory) importable
# so `import app` / `import finance` resolve to the real application modules
# regardless of the directory pytest is invoked from.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as bbi_app  # noqa: E402  (import must follow the sys.path fix-up)


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    """The `app` module, rewired to use a fresh temp SQLite DB for this test.

    Each test gets its own database file under pytest's tmp_path, so tests
    never share state and can run in any order.
    """
    db_path = tmp_path / "bank_test.db"
    monkeypatch.setattr(bbi_app, "DB_FILE", str(db_path))
    bbi_app.init_db()
    bbi_app.app.config.update(TESTING=True)
    yield bbi_app


@pytest.fixture()
def client(app_module):
    """A Flask test client bound to the temp-DB app instance."""
    return app_module.app.test_client()


@pytest.fixture()
def db_conn(app_module):
    """A raw sqlite3 connection to the same temp DB the app is using.

    Handy for asserting on ledger state directly instead of scraping HTML.
    The app closes its own per-request connection via teardown_appcontext,
    so there is no conflict opening a second, read-oriented connection here.
    """
    conn = sqlite3.connect(app_module.DB_FILE)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
