"""Accounting agent — LangGraph StateGraph that produces a P&L from the ledger.

Graph:  gather → compute → (narrate | template) → END

Reads the `transactions` ledger, aggregates by kind, and returns a profit-and-loss
summary. The narrative node adds a short CFO-style commentary (Claude or template).
"""
import json
from typing import TypedDict

from langgraph.graph import StateGraph, END

from db import get_conn
from agents.base import Agent
from agents.llm import get_chat_model, invoke_text


class AcctState(TypedDict, total=False):
    totals: dict
    pl: dict
    narrative: str
    source: str


def _gather(state: AcctState) -> AcctState:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT kind, COALESCE(SUM(amount),0) total, COUNT(*) n FROM transactions GROUP BY kind"
        ).fetchall()
    totals = {r["kind"]: {"total": round(r["total"], 2), "count": r["n"]} for r in rows}
    return {"totals": totals}


def _compute(state: AcctState) -> AcctState:
    t = state["totals"]
    revenue = t.get("sale", {}).get("total", 0.0)
    cogs = t.get("purchase", {}).get("total", 0.0)
    expenses = t.get("expense", {}).get("total", 0.0)
    gross_profit = round(revenue - cogs, 2)
    net_profit = round(gross_profit - expenses, 2)
    gross_margin_pct = round((gross_profit / revenue * 100), 1) if revenue else 0.0
    pl = {
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "operating_expenses": expenses,
        "net_profit": net_profit,
        "gross_margin_pct": gross_margin_pct,
        "transaction_counts": {k: v["count"] for k, v in state["totals"].items()},
    }
    return {"pl": pl}


def _narrate(state: AcctState) -> AcctState:
    model = get_chat_model(max_tokens=280)
    system = (
        "You are an accounting agent. In 2-3 sentences give a plain-English read of this P&L: "
        "is the business profitable, and the single biggest lever to improve net profit?"
    )
    try:
        text = invoke_text(model, system, json.dumps(state["pl"], indent=2))
        return {"narrative": text, "source": "claude"}
    except Exception:
        return {"narrative": _template(state["pl"]), "source": "fallback"}


def _template_node(state: AcctState) -> AcctState:
    return {"narrative": _template(state["pl"]), "source": "fallback"}


def _template(pl: dict) -> str:
    verdict = "profitable" if pl["net_profit"] > 0 else "not yet profitable"
    lever = "grow revenue / raise prices" if pl["gross_margin_pct"] < 30 else "cut input costs (COGS)"
    return (
        f"The business is {verdict}: revenue {pl['revenue']}, COGS {pl['cogs']}, "
        f"gross profit {pl['gross_profit']} ({pl['gross_margin_pct']}%), net profit {pl['net_profit']}. "
        f"Biggest lever: {lever}."
    )


def _route(state: AcctState) -> str:
    return "narrate" if get_chat_model() else "template"


def _build_graph():
    g = StateGraph(AcctState)
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


class AccountingAgent(Agent):
    name = "accounting"
    title = "Accounting Agent"
    description = "Builds a profit-and-loss statement from the ledger with a plain-English read."
    framework = "langgraph"

    def __init__(self):
        self._graph = _build_graph()

    def handle(self, payload: dict) -> dict:
        final = self._graph.invoke({})
        result = dict(final["pl"])
        result["narrative"] = final["narrative"]
        result["reasoning_source"] = final["source"]
        return result
