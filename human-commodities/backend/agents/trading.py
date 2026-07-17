"""Trading agent — LangGraph StateGraph. Advisory only (never moves money).

Graph:  gather → analyze → (narrate | template) → END

Suggests input-sourcing reorder quantities and an optimal sell price per product,
based on catalog economics. It only *recommends* — no funds are ever transferred.
"""
import json
from typing import TypedDict

from langgraph.graph import StateGraph, END

from db import get_conn
from agents.base import Agent
from agents.llm import get_chat_model, invoke_text

TARGET_MARGIN_PCT = 40.0   # desired gross margin
LOW_STOCK_UNITS = 500.0    # reorder trigger


class TradeState(TypedDict, total=False):
    product_id: int
    products: list
    ideas: list
    narrative: str
    source: str


def _gather(state: TradeState) -> TradeState:
    with get_conn() as conn:
        if state.get("product_id"):
            rows = conn.execute("SELECT * FROM products WHERE id = ?", (state["product_id"],)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    return {"products": [dict(r) for r in rows]}


def _analyze(state: TradeState) -> TradeState:
    ideas = []
    for p in state["products"]:
        cost, sell = p["cost_price"], p["sell_price"]
        margin_pct = round((sell - cost) / sell * 100, 1) if sell else 0.0
        target_price = round(cost / (1 - TARGET_MARGIN_PCT / 100), 2) if cost else sell
        ideas.append({
            "product": p["name"],
            "current_margin_pct": margin_pct,
            "suggested_sell_price": target_price,
            "price_action": "raise" if target_price > sell else "hold",
            "reorder_inputs": p["stock_qty"] < LOW_STOCK_UNITS,
            "stock_qty": p["stock_qty"],
        })
    return {"ideas": ideas}


def _facts(state: TradeState) -> dict:
    return {"target_margin_pct": TARGET_MARGIN_PCT, "ideas": state["ideas"]}


def _narrate(state: TradeState) -> TradeState:
    model = get_chat_model(max_tokens=320)
    system = (
        "You are a commodity trading advisor. From these per-product ideas, give the top 2-3 "
        "sourcing/pricing moves in 3 sentences. Advisory only — never instruct to transfer money."
    )
    try:
        return {"narrative": invoke_text(model, system, json.dumps(_facts(state), indent=2)), "source": "claude"}
    except Exception:
        return {"narrative": _template(state), "source": "fallback"}


def _template_node(state: TradeState) -> TradeState:
    return {"narrative": _template(state), "source": "fallback"}


def _template(state: TradeState) -> str:
    raises = [i["product"] for i in state["ideas"] if i["price_action"] == "raise"]
    reorder = [i["product"] for i in state["ideas"] if i["reorder_inputs"]]
    parts = [f"Target gross margin: {TARGET_MARGIN_PCT}%."]
    parts.append(f"Consider raising price on: {', '.join(raises)}." if raises else "Prices are at/above target margin.")
    parts.append(f"Reorder inputs for low stock: {', '.join(reorder)}." if reorder else "Input stock levels look healthy.")
    parts.append("Advisory only — execute any purchase/sale manually.")
    return " ".join(parts)


def _route(state: TradeState) -> str:
    return "narrate" if get_chat_model() else "template"


def _build_graph():
    g = StateGraph(TradeState)
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


class TradingAgent(Agent):
    name = "trading"
    title = "Trading Agent"
    description = "Advises on input reorders and optimal sell prices (advisory only — never moves money)."
    framework = "langgraph"

    def __init__(self):
        self._graph = _build_graph()

    def handle(self, payload: dict) -> dict:
        final = self._graph.invoke({"product_id": payload.get("product_id")})
        return {"ideas": final["ideas"], "narrative": final["narrative"], "reasoning_source": final["source"]}
