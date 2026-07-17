"""Business agent — LangGraph StateGraph. Strategy & KPIs (advisory).

Graph:  gather → compute → (narrate | template) → END

Rolls up catalog + ledger into headline KPIs and a strategic recommendation.
"""
import json
from typing import TypedDict

from langgraph.graph import StateGraph, END

from db import get_conn
from agents.base import Agent
from agents.llm import get_chat_model, invoke_text


class BizState(TypedDict, total=False):
    kpis: dict
    narrative: str
    source: str


def _gather(state: BizState) -> BizState:
    with get_conn() as conn:
        prod = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(stock_qty*sell_price),0) inv FROM products"
        ).fetchone()
        sales = conn.execute("SELECT COALESCE(SUM(amount),0) v FROM transactions WHERE kind='sale'").fetchone()
        cogs = conn.execute("SELECT COALESCE(SUM(amount),0) v FROM transactions WHERE kind='purchase'").fetchone()
        orders = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(total),0) v FROM orders").fetchone()
    revenue = round(sales["v"], 2)
    kpis = {
        "products": prod["c"],
        "inventory_value": round(prod["inv"], 2),
        "revenue": revenue,
        "cogs": round(cogs["v"], 2),
        "net_profit": round(revenue - cogs["v"], 2),
        "orders": orders["c"],
        "avg_order_value": round(orders["v"] / orders["c"], 2) if orders["c"] else 0.0,
    }
    return {"kpis": kpis}


def _compute(state: BizState) -> BizState:
    k = state["kpis"]
    # Simple sell-through proxy: revenue vs inventory tied up.
    k["sell_through_pct"] = round(k["revenue"] / k["inventory_value"] * 100, 2) if k["inventory_value"] else 0.0
    return {"kpis": k}


def _narrate(state: BizState) -> BizState:
    model = get_chat_model(max_tokens=340)
    system = (
        "You are a business strategy advisor for a commodities venture. From these KPIs, give a "
        "one-paragraph read: current health and the single highest-leverage growth move."
    )
    try:
        return {"narrative": invoke_text(model, system, json.dumps(state["kpis"], indent=2)), "source": "claude"}
    except Exception:
        return {"narrative": _template(state["kpis"]), "source": "fallback"}


def _template_node(state: BizState) -> BizState:
    return {"narrative": _template(state["kpis"]), "source": "fallback"}


def _template(k: dict) -> str:
    health = "profitable" if k["net_profit"] > 0 else "pre-profit (inventory being built)"
    lever = (
        "convert inventory to sales — push distribution/marketing"
        if k["sell_through_pct"] < 50 else "expand the catalog into adjacent commodities"
    )
    return (
        f"The venture is {health}: {k['products']} products, inventory value {k['inventory_value']}, "
        f"revenue {k['revenue']}, net profit {k['net_profit']}, sell-through {k['sell_through_pct']}%. "
        f"Highest-leverage move: {lever}."
    )


def _route(state: BizState) -> str:
    return "narrate" if get_chat_model() else "template"


def _build_graph():
    g = StateGraph(BizState)
    g.add_node("gather", _gather)
    g.add_node("compute", _compute)
    g.add_node("narrate", _narrate)
    g.add_node("template", _template_node)
    g.set_entry_point("gather")
    g.add_edge("gather", "compute")
    g.add_conditional_edges("compute", _route, {"narrate": "narrate", "template": "template"})
    g.add_edge("narrate", END)
    g.add_edge("template", END)
    return g.compile()


class BusinessAgent(Agent):
    name = "business"
    title = "Business Agent"
    description = "Rolls up KPIs and recommends the highest-leverage growth move."
    framework = "langgraph"

    def __init__(self):
        self._graph = _build_graph()

    def handle(self, payload: dict) -> dict:
        final = self._graph.invoke({})
        result = dict(final["kpis"])
        result["narrative"] = final["narrative"]
        result["reasoning_source"] = final["source"]
        return result
