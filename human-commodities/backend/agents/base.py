"""Base class shared by every agent."""
import json

from db import get_conn


class Agent:
    name = "agent"
    title = "Agent"
    description = "Base agent"
    live = True  # False for stubs reserved for a later wave
    framework = "custom"  # live agents are built on "langgraph"

    def handle(self, payload: dict) -> dict:
        """Override in subclasses. Return a JSON-serialisable dict."""
        raise NotImplementedError

    def run(self, payload: dict) -> dict:
        """Execute the agent, persist a run record, return the result."""
        try:
            result = self.handle(payload or {})
            status = "ok"
        except Exception as exc:
            result = {"error": str(exc)}
            status = "error"
        self._log(payload, result, status)
        return {"agent": self.name, "status": status, "result": result}

    def _log(self, payload, result, status):
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO agent_runs (agent, input, output, status) VALUES (?,?,?,?)",
                (
                    self.name,
                    json.dumps(payload or {})[:4000],
                    json.dumps(result)[:8000],
                    status,
                ),
            )
