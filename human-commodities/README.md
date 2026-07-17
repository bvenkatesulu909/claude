# Human Commodities

An **AI-agent platform for manufacturing and selling everyday human-needs commodities** —
food, hygiene, textiles, staples, anything people actually use. Agents plan production,
research markets, run the storefront, and keep the books.

Domain-agnostic by design: the **product catalog is data**, so the same system works for
any commodity you list.

## Architecture

```
human-commodities/
├── backend/            Flask REST API + SQLite storage + agents
│   ├── app.py          API routes
│   ├── db.py           schema + connection helper
│   ├── seed.py         demo catalog (8 commodities)
│   └── agents/
│       ├── llm.py      Claude wrapper (graceful offline fallback)
│       ├── planning.py Planning agent (LIVE)
│       ├── research.py Research agent (LIVE)
│       └── registry.py + stubs: manufacturing, trading, accounting, business, retailer
├── frontend/           React + Vite console (Dashboard / Catalog / Agents / Storefront / Outputs)
└── landing/            Static marketing landing page
```

## Agents

All seven agents are live LangGraph graphs.

| Agent          | Status | What it does |
|----------------|--------|--------------|
| Planning       | ✅ live | Costed production plan: BOM, timeline, margin |
| Research       | ✅ live | Market brief: demand, competition, pricing, risks |
| Manufacturing  | ✅ live | Executes a run: adds stock, books input cost |
| Accounting     | ✅ live | P&L from the ledger with a plain-English read |
| Trading        | ✅ live | Reorder + optimal-price advice (advisory; never moves money) |
| Business       | ✅ live | KPI roll-up + highest-leverage growth move |
| Retailer       | ✅ live | Low-stock alerts, best sellers, price nudges |

### Orchestration

A top-level **LangGraph orchestration graph** (`agents/orchestrator.py`) chains all seven
agents end-to-end for one product — the core production loop, then the advisory tail:

```
research → planning → manufacturing → accounting → trading → retailer → business → END
```

Exposed as `POST /api/orchestrate {product_id, quantity, target_days}` and driven from the
**Pipeline** tab in the console.

## AI framework: LangGraph (with offline fallback)

The live agents are built as **LangGraph `StateGraph`s** and reason with Claude through
`langchain-anthropic`:

```
Planning:  fetch → compute → (narrate | template) → persist → END
Research:  gather → (analyze | template) → persist → END
```

A conditional edge after the compute/gather node routes to the live-Claude node when
`ANTHROPIC_API_KEY` is set, or to a deterministic `template` node when offline. **Without a
key the platform still runs end-to-end** — Planning always computes real numbers from catalog
data in the `compute` node; only the narrative prose degrades to a template. Set the key to
upgrade to live Claude analysis.

## Run it

### 1. Backend (port 5060)
```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # + anthropic for live Claude
.venv/Scripts/python seed.py        # one-time demo catalog
.venv/Scripts/python app.py
```

### 2. Frontend (port 5173, proxies /api → 5060)
```bash
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173** for the console, or **http://127.0.0.1:5060/** for the landing page.

### Single-server (production) mode
Build the console once and let Flask serve everything from one process:
```bash
cd frontend && npm run build      # emits frontend/dist (served by Flask at /app)
cd ../backend && .venv/Scripts/python app.py
```
Then **http://127.0.0.1:5060/** is the landing page and **http://127.0.0.1:5060/app** is the
console — same origin, so no CORS/proxy needed. For a real deployment, put a WSGI server
(e.g. `waitress-serve --port 5060 app:app`) in front.

### Live Claude (optional)
```bash
.venv/Scripts/python -m pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...      # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
```

## API quick reference

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/dashboard` | summary stats |
| GET/POST | `/api/products` | catalog CRUD (+ PUT/DELETE `/<id>`) |
| GET  | `/api/agents` | list agents |
| POST | `/api/agents/<name>/run` | run an agent |
| POST | `/api/orchestrate` | run the full research→plan→produce→P&L loop |
| GET/POST | `/api/orders` | storefront (auto stock + ledger) |
| GET  | `/api/plans` · `/api/reports` · `/api/transactions` | agent outputs + ledger |

## Roadmap
1. ✅ ~~Wire Manufacturing + Accounting to real LangGraph logic.~~
2. ✅ ~~Orchestration graph: Research → Planning → Manufacturing → Accounting.~~
3. ✅ ~~All seven agents live as LangGraph graphs (added Trading, Retailer, Business).~~
4. Extend orchestration with an advisory tail (Trading → Retailer → Business) after Accounting.
5. Persist agent outputs for Trading/Retailer/Business (currently returned live, logged in `agent_runs`).
6. Auth + multi-tenant so several entrepreneurs share one deployment.
7. Deploy (backend on a host + built frontend), like the Bharath Bank Netlify setup.
