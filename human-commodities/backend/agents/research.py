"""Research agent — implemented as a LangGraph StateGraph.

Graph:  gather → (analyze | template) → persist → END

`gather` resolves the topic and any catalog context; the conditional edge routes to
the live-Claude `analyze` node or the deterministic `template` node when offline.
"""
from typing import TypedDict

from langgraph.graph import StateGraph, END

from db import get_conn
from agents.base import Agent
from agents.llm import get_chat_model, invoke_text


class ResearchState(TypedDict, total=False):
    topic: str
    product_id: int
    product: dict
    content: str
    source: str
    report_id: int


def _gather(state: ResearchState) -> ResearchState:
    topic = (state.get("topic") or "").strip()
    product = None
    if state.get("product_id"):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id = ?", (state["product_id"],)
            ).fetchone()
        if row:
            product = dict(row)
            topic = topic or product["name"]
    if not topic:
        raise ValueError("topic or product_id is required")
    return {"topic": topic, "product": product or {}}


def _analyze(state: ResearchState) -> ResearchState:
    model = get_chat_model(max_tokens=900)
    system = (
        "You are a commodity market-research analyst. Produce a structured brief with these "
        "sections: Demand drivers, Competitive landscape, Pricing outlook, Key risks, and a "
        "one-line Recommendation. Be concrete and concise."
    )
    p = state.get("product") or {}
    ctx = f"Topic: {state['topic']}\n"
    if p:
        ctx += (
            f"Catalog data: category={p['category']}, cost={p['cost_price']}, "
            f"sell={p['sell_price']}, stock={p['stock_qty']} {p['unit']}\n"
        )
    try:
        return {"content": invoke_text(model, system, ctx), "source": "claude"}
    except Exception:
        return {"content": _template_brief(state["topic"], p), "source": "fallback"}


def _template(state: ResearchState) -> ResearchState:
    return {"content": _template_brief(state["topic"], state.get("product") or {}), "source": "fallback"}


def _persist(state: ResearchState) -> ResearchState:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO research_reports (topic, content) VALUES (?,?)",
            (state["topic"], state["content"]),
        )
        return {"report_id": cur.lastrowid}


def _template_brief(topic: str, product: dict) -> str:
    price_line = ""
    if product:
        margin = product["sell_price"] - product["cost_price"]
        price_line = (
            f"- Current unit economics: cost {product['cost_price']}, "
            f"sell {product['sell_price']}, margin {round(margin, 2)}/{product['unit']}.\n"
        )
    return (
        f"# Market Research Brief — {topic}\n"
        "*(offline template — set ANTHROPIC_API_KEY for live Claude analysis)*\n\n"
        "## Demand drivers\n"
        f"- Everyday human need for {topic}; demand is relatively inelastic.\n"
        "- Population growth and urbanisation expand the addressable market.\n\n"
        "## Competitive landscape\n"
        "- Fragmented: local producers compete on price and availability.\n"
        "- Differentiation via quality, reliability, and distribution reach.\n\n"
        "## Pricing outlook\n"
        f"{price_line}"
        "- Input-cost volatility is the main pricing risk to monitor.\n\n"
        "## Key risks\n"
        "- Raw-material supply shocks; regulatory/quality compliance; logistics.\n\n"
        "## Recommendation\n"
        f"- Proceed with a small pilot batch of {topic}, validate demand, then scale."
    )


def _route(state: ResearchState) -> str:
    return "analyze" if get_chat_model() else "template"


def _build_graph():
    g = StateGraph(ResearchState)
    g.add_node("gather", _gather)
    g.add_node("analyze", _analyze)
    g.add_node("template", _template)
    g.add_node("persist", _persist)
    g.set_entry_point("gather")
    g.add_conditional_edges("gather", _route, {"analyze": "analyze", "template": "template"})
    g.add_edge("analyze", "persist")
    g.add_edge("template", "persist")
    g.add_edge("persist", END)
    return g.compile()


class ResearchAgent(Agent):
    name = "research"
    title = "Research Agent"
    description = "Generates a market-research brief: demand drivers, competition, pricing, risks, recommendation."
    framework = "langgraph"

    def __init__(self):
        self._graph = _build_graph()

    def handle(self, payload: dict) -> dict:
        topic = (payload.get("topic") or "").strip()
        product_id = payload.get("product_id")
        if not topic and not product_id:
            raise ValueError("topic or product_id is required")

        final = self._graph.invoke({"topic": topic, "product_id": product_id})
        return {
            "report_id": final["report_id"],
            "topic": final["topic"],
            "content": final["content"],
            "reasoning_source": final["source"],
        }
