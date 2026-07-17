"""Business orchestrator — a LangGraph StateGraph that runs the whole loop.

Graph:  research → planning → manufacturing → accounting → END

Each node invokes a specialised agent and threads its output into shared state, so a
single call takes a product from market research all the way to a booked P&L. This is
the multi-agent hand-off that the individual agents can't do alone.
"""
from typing import TypedDict

from langgraph.graph import StateGraph, END

from agents.registry import get_agent


class FlowState(TypedDict, total=False):
    product_id: int
    quantity: float
    target_days: int
    research: dict
    planning: dict
    manufacturing: dict
    accounting: dict
    trading: dict
    retailer: dict
    business: dict


def _research_node(state: FlowState) -> FlowState:
    out = get_agent("research").run({"product_id": state["product_id"]})
    return {"research": out["result"]}


def _planning_node(state: FlowState) -> FlowState:
    out = get_agent("planning").run(
        {
            "product_id": state["product_id"],
            "quantity": state["quantity"],
            "target_days": state.get("target_days", 14),
        }
    )
    return {"planning": out["result"]}


def _manufacturing_node(state: FlowState) -> FlowState:
    plan_id = (state.get("planning") or {}).get("plan_id")
    out = get_agent("manufacturing").run({"plan_id": plan_id})
    return {"manufacturing": out["result"]}


def _accounting_node(state: FlowState) -> FlowState:
    out = get_agent("accounting").run({})
    return {"accounting": out["result"]}


def _trading_node(state: FlowState) -> FlowState:
    out = get_agent("trading").run({"product_id": state["product_id"]})
    return {"trading": out["result"]}


def _retailer_node(state: FlowState) -> FlowState:
    out = get_agent("retailer").run({})
    return {"retailer": out["result"]}


def _business_node(state: FlowState) -> FlowState:
    out = get_agent("business").run({})
    return {"business": out["result"]}


def _build_graph():
    g = StateGraph(FlowState)
    g.add_node("research", _research_node)
    g.add_node("planning", _planning_node)
    g.add_node("manufacturing", _manufacturing_node)
    g.add_node("accounting", _accounting_node)
    g.add_node("trading", _trading_node)
    g.add_node("retailer", _retailer_node)
    g.add_node("business", _business_node)
    g.set_entry_point("research")
    # Core production loop, then the advisory tail.
    g.add_edge("research", "planning")
    g.add_edge("planning", "manufacturing")
    g.add_edge("manufacturing", "accounting")
    g.add_edge("accounting", "trading")
    g.add_edge("trading", "retailer")
    g.add_edge("retailer", "business")
    g.add_edge("business", END)
    return g.compile()


_GRAPH = _build_graph()

STAGES = ["research", "planning", "manufacturing", "accounting", "trading", "retailer", "business"]


def run_flow(product_id: int, quantity: float, target_days: int = 14) -> dict:
    if not product_id:
        raise ValueError("product_id is required")
    if quantity <= 0:
        raise ValueError("quantity must be > 0")
    final = _GRAPH.invoke(
        {"product_id": product_id, "quantity": quantity, "target_days": target_days}
    )
    return {stage: final.get(stage) for stage in STAGES}
