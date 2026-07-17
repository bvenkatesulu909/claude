"""Retailer agent — LangGraph StateGraph. Storefront optimisation (advisory).

Graph:  gather → analyze → (narrate | template) → END

Surfaces low-stock alerts, best sellers (from orders), and price nudges.
"""
import json
from typing import TypedDict

from langgraph.graph import StateGraph, END

from db import get_conn
from agents.base import Agent
from agents.llm import get_chat_model, invoke_text

LOW_STOCK_UNITS = 400.0


class RetailState(TypedDict, total=False):
    products: list
    top_sellers: list
    alerts: list
    narrative: str
    source: str


def _gather(state: RetailState) -> RetailState:
    with get_conn() as conn:
        products = [dict(r) for r in conn.execute("SELECT * FROM products ORDER BY id").fetchall()]
        top = conn.execute(
            """SELECT pr.name, COALESCE(SUM(o.quantity),0) qty, COALESCE(SUM(o.total),0) revenue
               FROM orders o JOIN products pr ON pr.id = o.product_id
               GROUP BY o.product_id ORDER BY revenue DESC LIMIT 5"""
        ).fetchall()
    return {"products": products, "top_sellers": [dict(r) for r in top]}


def _analyze(state: RetailState) -> RetailState:
    alerts = []
    for p in state["products"]:
        if p["stock_qty"] < LOW_STOCK_UNITS:
            alerts.append({"type": "low_stock", "product": p["name"], "stock_qty": p["stock_qty"]})
        margin_pct = round((p["sell_price"] - p["cost_price"]) / p["sell_price"] * 100, 1) if p["sell_price"] else 0
        if margin_pct < 20:
            alerts.append({"type": "thin_margin", "product": p["name"], "margin_pct": margin_pct})
    return {"alerts": alerts}


def _facts(state: RetailState) -> dict:
    return {"top_sellers": state["top_sellers"], "alerts": state["alerts"]}


def _narrate(state: RetailState) -> RetailState:
    model = get_chat_model(max_tokens=320)
    system = (
        "You are a retail operations advisor. From the best sellers and alerts, give the top 3 "
        "storefront actions (restock, reprice, promote) in 3 sentences."
    )
    try:
        return {"narrative": invoke_text(model, system, json.dumps(_facts(state), indent=2)), "source": "claude"}
    except Exception:
        return {"narrative": _template(state), "source": "fallback"}


def _template_node(state: RetailState) -> RetailState:
    return {"narrative": _template(state), "source": "fallback"}


def _template(state: RetailState) -> str:
    low = [a["product"] for a in state["alerts"] if a["type"] == "low_stock"]
    thin = [a["product"] for a in state["alerts"] if a["type"] == "thin_margin"]
    best = state["top_sellers"][0]["name"] if state["top_sellers"] else "—"
    parts = [f"Best seller by revenue: {best}."]
    parts.append(f"Restock soon: {', '.join(low)}." if low else "No low-stock alerts.")
    parts.append(f"Review thin margins on: {', '.join(thin)}." if thin else "Margins are healthy across the storefront.")
    return " ".join(parts)


def _route(state: RetailState) -> str:
    return "narrate" if get_chat_model() else "template"


def _build_graph():
    g = StateGraph(RetailState)
    g.add_node("gather", _gather)
    g.add_node("analyze", _analyze)
    g.add_node("narrate", _narrate)
    g.add_node("template", _template_node)
    g.set_entry_point("gather")
    g.add_edge("gather", "analyze")
    g.add_conditional_edges("analyze", _route, {"narrate": "narrate", "template": "template"})
    g.add_edge("narrate", END)
    g.add_edge("template", END)
    return g.compile()


class RetailerAgent(Agent):
    name = "retailer"
    title = "Retailer Agent"
    description = "Storefront advisor: low-stock alerts, best sellers, and price nudges."
    framework = "langgraph"

    def __init__(self):
        self._graph = _build_graph()

    def handle(self, payload: dict) -> dict:
        final = self._graph.invoke({})
        return {
            "top_sellers": final["top_sellers"],
            "alerts": final["alerts"],
            "narrative": final["narrative"],
            "reasoning_source": final["source"],
        }
