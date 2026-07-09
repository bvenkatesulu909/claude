# Deploying Bharath Bank of India

This is a self-contained **Flask + SQLite** app. There is **no external database
to provision** — the database is a plain file (`bank.db`) that the app creates
and seeds automatically on first boot via `init_db()`. You only need a Python
web host.

## What's in this folder (the deployment artifacts)

| File               | Purpose                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| `requirements.txt` | Python deps: `Flask` (ships with Werkzeug) and `gunicorn` (WSGI server).|
| `wsgi.py`          | Gunicorn entry point. Imports `app`, runs `init_db()`, exposes `app`.   |
| `Procfile`         | Process command (Railway / Heroku-style hosts read this).               |
| `render.yaml`      | Render "Blueprint" — one-click infrastructure definition.               |
| `runtime.txt`      | Pins Python to `3.12.6` (a widely supported version).                   |

The start command is always:

```
gunicorn wsgi:app --bind 0.0.0.0:$PORT
```

`$PORT` is injected by the host. `wsgi:app` means "import `app` from `wsgi.py`".

> **IMPORTANT — repo subpath.** This app lives in the repository subfolder
> **`bharath-bank/`**, not at the repo root. Whatever host you use, its
> **root directory / working directory must be set to `bharath-bank`** so it
> finds `requirements.txt`, `wsgi.py`, and the `templates/` + `static/` folders.
> `render.yaml` already does this via `rootDir: bharath-bank`. On Railway you
> set it manually (see below).

> **IMPORTANT — data is ephemeral on free tiers.** The SQLite file lives on the
> host's disk. On free plans that disk is wiped on every deploy/restart, so
> registered users and transactions reset and the app re-seeds the reference
> data (schemes, loan products). This is expected for a demo. See
> "Persisting data" at the end to keep data across deploys.

---

## Option A — Render (recommended)

### A1. Blueprint deploy (uses `render.yaml`, fully automated)

1. Push this repository to GitHub (see "Pushing to GitHub" below).
2. Go to <https://dashboard.render.com> and sign in.
3. Click **New +** (top right) -> **Blueprint**.
4. Connect your GitHub account if prompted, then **select this repository**.
5. Render detects `bharath-bank/render.yaml`. Review the plan — it will create a
   free web service named **bharath-bank-of-india** with:
   - Root dir `bharath-bank`
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn wsgi:app --bind 0.0.0.0:$PORT`
   - Env var `BBI_SECRET` auto-generated (Flask session secret).
6. Click **Apply**. Wait for the build + deploy to finish (a few minutes).
7. Open the service URL (e.g. `https://bharath-bank-of-india.onrender.com`).

> Free web services **sleep after ~15 min of inactivity**; the first request
> after sleeping takes ~30–60s to wake. That's normal.

### A2. Manual web service (no `render.yaml`)

Use this if you'd rather click through the UI:

1. Push the repo to GitHub.
2. Render dashboard -> **New +** -> **Web Service** -> select the repo.
3. Fill in the settings:
   - **Root Directory**: `bharath-bank`  ← required (app is in a subfolder)
   - **Runtime / Language**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:app --bind 0.0.0.0:$PORT`
   - **Instance Type**: `Free`
4. Under **Environment**, add a variable:
   - **Key** `BBI_SECRET`, **Value** = any long random string
     (e.g. run `python -c "import secrets; print(secrets.token_hex(32))"`).
5. Click **Create Web Service**. Render builds and deploys automatically.

---

## Option B — Railway

Railway reads the `Procfile` for the start command.

### B1. From the Railway dashboard (GitHub repo)

1. Push the repo to GitHub.
2. Go to <https://railway.app> and sign in.
3. Click **New Project** -> **Deploy from GitHub repo** -> pick this repo.
4. Open the created service -> **Settings**:
   - **Root Directory**: set to `bharath-bank`  ← required (app is in a subfolder).
   - **Start Command**: leave blank to use the `Procfile`, or set explicitly to
     `gunicorn wsgi:app --bind 0.0.0.0:$PORT`.
5. Go to the **Variables** tab and add:
   - `BBI_SECRET` = a long random string
     (`python -c "import secrets; print(secrets.token_hex(32))"`).
   - You do **not** need to set `PORT` — Railway provides it automatically.
6. Deploy runs automatically. When it's live, open **Settings -> Networking ->
   Generate Domain** to get a public URL.

### B2. From the Railway CLI

```bash
npm i -g @railway/cli          # install the CLI
railway login                  # opens a browser to authenticate
cd bharath-bank                # IMPORTANT: deploy from the app subfolder
railway init                   # create a new project (follow prompts)
railway variables --set "BBI_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")"
railway up                     # build & deploy the current folder
railway domain                 # generate a public URL
```

---

## Pushing to GitHub (first time)

From the **repository root** (the folder that contains `bharath-bank/`):

```bash
git init                       # if not already a git repo
git add .
git commit -m "Add Bharath Bank deployment config"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

Both Render and Railway then deploy from that GitHub repo.

---

## Quick local sanity check (optional)

You can confirm the WSGI entry point imports before deploying:

```bash
cd bharath-bank
python -c "import wsgi; print('OK', wsgi.app)"
```

To run it the way the host does (Linux/macOS; gunicorn is not supported on
native Windows):

```bash
cd bharath-bank
pip install -r requirements.txt
PORT=8000 gunicorn wsgi:app --bind 0.0.0.0:$PORT
```

Then open <http://localhost:8000>. On Windows, use `python app.py` instead
(that path uses Flask's built-in dev server).

---

## Persisting data across deploys (optional)

Because the app uses file-based SQLite, the data survives only as long as the
host's disk does. Free tiers reset it on each deploy.

- **Render**: attach a persistent disk (paid instance types only). In
  `render.yaml`, uncomment the `disk:` block — it mounts storage at
  `/opt/render/project/src`, which is where `bank.db` is written, so data
  survives restarts.
- **Railway**: add a **Volume** to the service and mount it at the app's working
  directory (where `bank.db` lives) so the file persists.

For a demo, the default ephemeral behavior is completely fine — the app simply
re-creates the schema and re-seeds the reference data on each boot.
