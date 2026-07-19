# SENTINEL — Defence Systems Operations Console (SIMULATION)

A full-stack (frontend + backend) demo whose **entire backend brain is a single
OpenAI Agents SDK agent** running on OpenRouter's **`tencent/hy3`** model.

> ⚠️ **Simulation only.** All units, positions and tracks are fictional,
> randomly generated data. This is a *defensive* situational-awareness /
> logistics-readiness monitoring demo — **not** a real, operational, or
> weapons-control system. The agent refuses offensive/targeting requests.

## What it does
- **Live dashboard** — readiness condition (RC-1…RC-4), force readiness by
  branch, order of battle, a "live" air/surface track picture (auto-refresh),
  and an incident log.
- **AI duty officer** — a chat panel backed by one Agents SDK agent that
  answers using tools and can log incidents.

## Architecture
```
Browser (templates/index.html + static/app.js)
   │  GET /api/dashboard   → fast, LLM-free data panels
   │  POST /api/chat       → the single agent (tool loop)
   ▼
Flask (app.py)
   └── Agent "SENTINEL"  [OpenAIChatCompletionsModel → OpenRouter tencent/hy3]
         tools: list_assets, get_asset, list_tracks, threat_posture,
                readiness_summary, log_incident, list_incidents
   └── data.py  (synthetic order of battle + simulated tracks + SQLite incidents)
```
One agent. Seven tools. It decides which to call per message and synthesizes
the answer — the classic Agents SDK loop, exposed through a web UI.

## Run
```bash
pip install -r requirements.txt
cp .env.example .env        # paste your OpenRouter key
python app.py               # http://127.0.0.1:5077
```

## OpenRouter notes (same two gotchas as any Agents-SDK-on-OpenRouter setup)
1. Wrap the model in `OpenAIChatCompletionsModel` over an `AsyncOpenAI` client
   pointed at `https://openrouter.ai/api/v1` (OpenRouter = Chat Completions, not
   the Responses API).
2. `set_tracing_disabled(True)` — no OpenAI key, so the tracing uploader is off.
