"""
SENTINEL — Defence Systems Operations Console (SIMULATION)

A full-stack demo whose entire backend "brain" is a SINGLE OpenAI Agents SDK
agent running on OpenRouter's `tencent/hy3` model. The agent is a defensive
"duty officer": it answers questions about a synthetic situational-awareness
and logistics-readiness picture by calling read-only tools, and can log
incidents to a local SQLite store.

All data is fictional. This is a monitoring/analytics demo, not a real or
operational defence system.
"""

import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import AsyncOpenAI

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
    set_tracing_disabled,
)

import data

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
set_tracing_disabled(True)

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "tencent/hy3")

# Model/agent are built only when a key is present, so the dashboard and health
# check still boot on a fresh deploy before the secret is configured. The chat
# endpoint reports clearly if the key is missing.
client = None
model = None
if API_KEY:
    client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY)
    model = OpenAIChatCompletionsModel(model=MODEL, openai_client=client)


# ---------------------------------------------------------------------------
# Agent tools (read-only situational awareness + one write: incident log)
# ---------------------------------------------------------------------------
@function_tool
def list_assets(branch: str = "") -> str:
    """List friendly force assets and their readiness %. Optionally filter by
    branch: Air, Naval, Land, Air Defence, Cyber, ISR."""
    return json.dumps(data.get_assets(branch or None))


@function_tool
def get_asset(asset_id: str) -> str:
    """Get details for one asset by its id (e.g. AIR-01, ADS-02)."""
    a = data.get_asset(asset_id)
    return json.dumps(a or {"error": f"No asset {asset_id}"})


@function_tool
def list_tracks(min_threat: int = 0) -> str:
    """List current SIMULATED radar tracks, optionally only those with a
    threat score >= min_threat (0-100)."""
    return json.dumps(data.get_tracks(min_threat))


@function_tool
def threat_posture() -> str:
    """Get the overall readiness condition derived from current tracks."""
    return json.dumps(data.threat_posture())


@function_tool
def readiness_summary() -> str:
    """Get average readiness % overall and broken down by branch."""
    return json.dumps(data.readiness_summary())


@function_tool
def log_incident(title: str, severity: str = "INFO", note: str = "") -> str:
    """Record an incident in the log. severity one of
    INFO, LOW, MEDIUM, HIGH, CRITICAL."""
    return json.dumps(data.log_incident(title, severity, note))


@function_tool
def list_incidents() -> str:
    """List the most recent logged incidents."""
    return json.dumps(data.list_incidents())


AGENT_INSTRUCTIONS = (
    "You are SENTINEL, an AI duty officer for a SIMULATED defence operations "
    "console. All data is synthetic/training data. Your role is purely "
    "DEFENSIVE situational awareness and logistics: report asset readiness, "
    "summarize radar tracks, assess the overall readiness condition, and log "
    "incidents when asked. Always call the tools to get real numbers instead "
    "of inventing them. Be concise and use a calm, professional command-center "
    "tone. If asked to do anything offensive, targeting, or weapon-control "
    "related, refuse and note this console is monitoring-only. When useful, "
    "end with a one-line 'Recommendation:'."
)

agent = None
if model is not None:
    agent = Agent(
        name="SENTINEL",
        instructions=AGENT_INSTRUCTIONS,
        model=model,
        tools=[
            list_assets,
            get_asset,
            list_tracks,
            threat_posture,
            readiness_summary,
            log_incident,
            list_incidents,
        ],
    )


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder=os.path.join(HERE, "templates"),
    static_folder=os.path.join(HERE, "static"),
)
data.init_db()


@app.route("/")
def index():
    return render_template("index.html", model=MODEL)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "agent": bool(agent), "model": MODEL})


@app.route("/api/dashboard")
def dashboard():
    """Live panels — pulled directly from the data layer (fast, no LLM)."""
    return jsonify(
        {
            "assets": data.get_assets(),
            "tracks": data.get_tracks(),
            "threat": data.threat_posture(),
            "readiness": data.readiness_summary(),
            "incidents": data.list_incidents(),
        }
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    """The single agent handles the message end-to-end (tool loop included)."""
    if agent is None:
        return jsonify({"error": "OPENROUTER_API_KEY not configured on the server."}), 503
    msg = (request.get_json(silent=True) or {}).get("message", "").strip()
    if not msg:
        return jsonify({"error": "empty message"}), 400
    try:
        result = Runner.run_sync(agent, msg)
        return jsonify({"reply": result.final_output})
    except Exception as e:  # surface model/network errors to the UI
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 502


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5077, threaded=True, debug=False)
