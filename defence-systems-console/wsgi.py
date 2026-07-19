"""Production entrypoint: init the DB, then serve with waitress on $PORT.

`application` is exposed for WSGI servers; running this module directly starts
a waitress server bound to 0.0.0.0:$PORT (what the Docker image / Render use).
"""
import os

import data
from app import app

data.init_db()
application = app

if __name__ == "__main__":
    from waitress import serve

    port = int(os.environ.get("PORT", "8080"))
    print(f"[wsgi] serving SENTINEL console on 0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port)
