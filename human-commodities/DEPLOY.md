# Deploying Human Commodities

The app is a **single container**: a multi-stage Dockerfile builds the React console,
then a Python image serves the API, the landing page (`/`), and the console (`/app`) via
waitress. Any Docker-capable host works.

## Option A — Render (one click, recommended)
1. Push this repo to GitHub (already done if you're reading this there).
2. On [render.com](https://render.com): **New → Blueprint**, pick this repo.
3. Render reads [`render.yaml`](render.yaml) and provisions a free Docker web service.
4. (Optional) set `ANTHROPIC_API_KEY` in the service's Environment tab for live Claude
   reasoning. Without it the agents run their offline deterministic paths.
5. Your app is live at `https://human-commodities.onrender.com` (landing at `/`, console at `/app`).

## Option B — Railway / Fly.io
Both auto-detect the Dockerfile.
- **Railway:** New Project → Deploy from GitHub repo → it builds the Dockerfile.
- **Fly.io:** `flyctl launch` in the repo root (uses the Dockerfile), then `flyctl deploy`.

## Option C — local container
```bash
docker build -t human-commodities .
docker run -p 8080:8080 -e ANTHROPIC_API_KEY=sk-ant-... human-commodities
# open http://localhost:8080
```

## Note on data persistence
The demo stores data in a local SQLite file. On free/ephemeral hosts the filesystem
resets on redeploy/restart, and the demo catalog is re-seeded automatically on boot.
For durable data, mount a persistent volume at `backend/` (or point `HC_DB_PATH` at one)
or swap SQLite for a managed Postgres.
