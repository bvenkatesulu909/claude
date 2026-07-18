"""Production entrypoint: init + seed the DB, then serve with waitress.

`application` is exposed for WSGI servers (gunicorn/waitress-serve); running this
module directly starts a waitress server on $PORT.
"""
import os

from db import init_db
from app import app

init_db()

# Seed a demo catalog on first boot (idempotent — skips if products already exist).
try:
    from seed import seed
    seed()
except Exception as exc:  # never let seeding crash startup
    print(f"[wsgi] seed skipped: {exc}")

application = app

if __name__ == "__main__":
    from waitress import serve

    port = int(os.environ.get("PORT", "8080"))
    print(f"[wsgi] serving Human Commodities on 0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port)
