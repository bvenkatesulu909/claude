# Bharath Bank — Flask + SQLite banking demo
FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal; sqlite3 driver ships with Python's stdlib.
COPY . .

RUN pip install --no-cache-dir flask gunicorn

# Run as a non-root user for good practice.
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app

USER app

EXPOSE 8000

# wsgi.py (created separately) imports `app` from app.py and calls init_db()
# before the app object is exposed, so gunicorn just needs to import it.
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000"]
