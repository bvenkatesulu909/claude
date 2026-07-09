# Running Bharath Bank in Docker

This folder contains a `Dockerfile`, `.dockerignore`, and `docker-compose.yml`
for running the Flask + SQLite banking demo in a container.

The image runs the app with `gunicorn` via a `wsgi.py` entrypoint
(`gunicorn wsgi:app --bind 0.0.0.0:8000`), listening on container port 8000.

## Option 1: Plain Docker

Build the image:

```sh
docker build -t bharath-bank .
```

Run it, mapping host port 5055 to the container's port 8000:

```sh
docker run -p 5055:8000 --name bharath-bank bharath-bank
```

To persist `bank.db` across container restarts/recreation, mount a volume
over `/app` (the app's working directory, where `bank.db` lives):

```sh
docker run -p 5055:8000 -v bharath-bank-data:/app --name bharath-bank bharath-bank
```

You can also pass the app secret at run time:

```sh
docker run -p 5055:8000 -e BBI_SECRET=some-long-random-string bharath-bank
```

Then open **http://localhost:5055** in your browser.

## Option 2: Docker Compose (recommended)

Build and start the `bank` service in the background:

```sh
docker compose up --build
```

Or detached:

```sh
docker compose up --build -d
```

This maps host `5055` -> container `8000`, sets `BBI_SECRET` (override it by
exporting `BBI_SECRET` in your shell or via a `.env` file before running
`docker compose up`), and stores `bank.db` in a named volume (`bank_data`)
mounted at `/app` so the database survives container recreation.

Then open **http://localhost:5055** in your browser.

To stop:

```sh
docker compose down
```

To stop and also wipe the persisted database volume:

```sh
docker compose down -v
```

### Note on the persistent volume

Because the named volume is mounted over the whole `/app` directory, Docker
seeds it from the image's `/app` contents the first time the container
starts. After that, the volume "shadows" `/app`, so rebuilding the image with
code changes won't show up until you also remove the volume
(`docker compose down -v`) or otherwise refresh it. This is a trade-off for
keeping the setup simple (single mount point, no code changes to `app.py`'s
`DB_FILE` path); if you want code updates to always take effect without
losing data, consider instead only mounting a dedicated `/app/data` subfolder
and pointing `DB_FILE` there in a future change.
