"""
WSGI entry point for Bharath Bank of India.

Gunicorn (or any WSGI server) imports this module and serves the callable
named ``app`` / ``application``. We call ``init_db()`` at import time so the
SQLite schema and reference/seed data exist before the first request is
handled — this is what makes the app boot cleanly on a fresh host where
bank.db does not yet exist.

Run locally with:  gunicorn wsgi:app --bind 0.0.0.0:$PORT
"""

from app import app, init_db

# Ensure tables exist and reference data is seeded before serving traffic.
init_db()

# Register admin blueprint (late import to avoid circular dependency).
from admin import admin_bp
app.register_blueprint(admin_bp)

# Gunicorn looks for "app" (as in `gunicorn wsgi:app`); many hosts default to
# "application". Expose both so either convention works.
application = app

__all__ = ["app", "application"]
