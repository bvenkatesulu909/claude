"""Planning agent — implemented as a LangGraph StateGraph.

Graph:  fetch → compute → (narrate | template) → persist → END

The conditional edge after `compute` routes to the live-Claude `narrate` node when
a chat model is available, or to the deterministic `template` node when offline.
The hard numbers (cost, revenue, margin, timeline) are always computed in `compute`,
so they never depend on the LLM.
"""
import json
import math
from typing import TypedDict

from langgraph.graph import StateGraph, END

from db import get_conn
from agents.base import Agent
from agents.llm import get_chat_model, invoke_text


class PlanState(TypedDict, total=False):
    product_id: int
    quantity: float
    target_days: int
    product: dict
    numbers: dict
    narrative: str
    source: str
    plan_id: int


# --------------------------------------------------------------------------- #
#  Graph nodes
# --------------------------------------------------------------------------- #
def _fetch(state: PlanState) -> PlanState:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id = ?", (state["product_id"],)
        ).fetchone()
    if not row:
        raise ValueError(f"product {state['product_id']} not found")
    return {"product": dict(row)}


def _compute(state: PlanState) -> PlanState:
    p = state["product"]
    qty = state["quantity"]
    days = state["target_days"]

    cost = round(p["cost_price"] * qty, 2)
    revenue = round(p["sell_price"] * qty, 2)
    margin = round(revenue - cost, 2)
    margin_pct = round((margin / revenue * 100), 1) if revenue else 0.0
    units_per_day = math.ceil(qty / max(days, 1))

    steps = [
        {"phase": "Procurement", "detail": f"Source raw inputs for {qty:g} {p['unit']} of {p['name']}", "days": max(1, days // 7)},
        {"phase": "Production", "detail": f"Manufacture ~{units_per_day:g} {p['unit']}/day", "days": max(1, days - days // 7 - 1)},
        {"phase": "QA & packaging", "detail": "Quality check and pack finished goods", "days": 1},
    ]
    numbers = {
        "product": p["name"], "category": p["category"], "quantity": qty,
        "unit": p["unit"], "units_per_day": units_per_day, "target_days": days,
        "cost_estimate": cost, "revenue_estimate": revenue,
        "gross_margin": margin, "gross_margin_pct": margin_pct, "steps": steps,
    }
    return {"numbers": numbers}


def _narrate(state: PlanState) -> PlanState:
    model = get_chat_model(max_tokens=500)
    system = (
        "You are a manufacturing planning agent for a consumer-commodities company. "
        "Given the computed numbers, write a concise, practical production plan: key risks, "
        "sequencing advice, and one cost-saving idea. 120 words max."
    )
    prompt = "Production numbers:\n" + json.dumps(state["numbers"], indent=2)
    try:
        return {"narrative": invoke_text(model, system, prompt), "source": "claude"}
    except Exception as exc:
        return {"narrative": _template_text(state["numbers"], error=str(exc)), "source": "fallback"}


def _template(state: PlanState) -> PlanState:
    return {"narrative": _template_text(state["numbers"]), "source": "fallback"}


def _persist(state: PlanState) -> PlanState:
    numbers = dict(state["numbers"])
    numbers["narrative"] = state["narrative"]
    numbers["reasoning_source"] = state["source"]
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO production_plans (product_id, quantity, status, plan_json) VALUES (?,?,?,?)",
            (state["product_id"], state["quantity"], "draft", json.dumps(numbers)),
        )
        plan_id = cur.lastrowid
    return {"plan_id": plan_id, "numbers": numbers}


def _template_text(numbers: dict, error: str | None = None) -> str:
    note = (
        "[offline mode — set ANTHROPIC_API_KEY for live Claude planning]"
        if not error else f"[Claude call failed, using template: {error}]"
    )
    m = numbers
    return (
        f"{note}\n\n"
        f"Plan for {m['quantity']:g} {m['unit']} of {m['product']} over {m['target_days']} days "
        f"(~{m['units_per_day']:g} {m['unit']}/day).\n"
        f"- Cost {m['cost_estimate']} → revenue {m['revenue_estimate']} "
        f"(gross margin {m['gross_margin']}, {m['gross_margin_pct']}%).\n"
        "- Sequence: secure inputs first, keep a QA buffer at the end.\n"
        "- Cost-saving idea: batch procurement to negotiate bulk input pricing."
    )


def _route(state: PlanState) -> str:
    return "narrate" if get_chat_model() else "template"


def _build_graph():
    g = StateGraph(PlanState)
    g.add_node("fetch", _fetch)
    g.add_node("compute", _compute)
    g.add_node("narrate", _narrate)
    g.add_node("template", _template)
    g.add_node("persist", _persist)
    g.set_entry_point("fetch")
    g.add_edge("fetch", "compute")
    g.add_conditional_edges("compute", _route, {"narrate": "narrate", "template": "template"})
    g.add_edge("narrate", "persist")
    g.add_edge("template", "persist")
    g.add_edge("persist", END)
    return g.compile()


# --------------------------------------------------------------------------- #
#  Agent wrapper
# --------------------------------------------------------------------------- #
class PlanningAgent(Agent):
    name = "planning"
    title = "Planning Agent"
    description = "Builds a production plan (materials, cost, timeline, margin) for a target quantity."
    framework = "langgraph"

    def __init__(self):
        self._graph = _build_graph()

    def handle(self, payload: dict) -> dict:
        product_id = payload.get("product_id")
        quantity = float(payload.get("quantity") or 0)
        target_days = int(payload.get("target_days") or 14)
        if not product_id:
            raise ValueError("product_id is required")
        if quantity <= 0:
            raise ValueError("quantity must be > 0")

        final = self._graph.invoke(
            {"product_id": product_id, "quantity": quantity, "target_days": target_days}
        )
        result = dict(final["numbers"])
        result["plan_id"] = final["plan_id"]
        return result
