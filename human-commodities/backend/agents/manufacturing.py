"""Manufacturing agent — LangGraph StateGraph that executes a production run.

Graph:  resolve → produce → (narrate | template) → END

`produce` is the side-effecting node: it adds finished goods to stock, books the
input cost as a purchase transaction, and marks the source plan as produced.
Accepts either a `plan_id` (uses that plan's product/quantity/cost) or an ad-hoc
`product_id` + `quantity`.
"""
import json
from typing import TypedDict

from langgraph.graph import StateGraph, END

from db import get_conn
from agents.base import Agent
from agents.llm import get_chat_model, invoke_text


class MfgState(TypedDict, total=False):
    plan_id: int
    product_id: int
    quantity: float
    product: dict
    input_cost: float
    new_stock: float
    narrative: str
    source: str


def _resolve(state: MfgState) -> MfgState:
    plan_id = state.get("plan_id")
    with get_conn() as conn:
        if plan_id:
            plan = conn.execute(
                "SELECT * FROM production_plans WHERE id = ?", (plan_id,)
            ).fetchone()
            if not plan:
                raise ValueError(f"plan {plan_id} not found")
            plan = dict(plan)
            pj = json.loads(plan["plan_json"] or "{}")
            product_id = plan["product_id"]
            quantity = plan["quantity"]
            input_cost = pj.get("cost_estimate")
        else:
            product_id = state.get("product_id")
            quantity = float(state.get("quantity") or 0)
            input_cost = None
        if not product_id or quantity <= 0:
            raise ValueError("plan_id, or product_id + positive quantity, is required")
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
    if not product:
        raise ValueError(f"product {product_id} not found")
    product = dict(product)
    if input_cost is None:
        input_cost = round(product["cost_price"] * quantity, 2)
    return {"product_id": product_id, "quantity": quantity, "product": product, "input_cost": input_cost}


def _produce(state: MfgState) -> MfgState:
    with get_conn() as conn:
        conn.execute(
            "UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?",
            (state["quantity"], state["product_id"]),
        )
        row = conn.execute(
            "SELECT stock_qty FROM products WHERE id = ?", (state["product_id"],)
        ).fetchone()
        conn.execute(
            "INSERT INTO transactions (kind, amount, description, ref_id) VALUES ('purchase',?,?,?)",
            (
                state["input_cost"],
                f"Production run: {state['quantity']:g} {state['product']['unit']} of {state['product']['name']}",
                state.get("plan_id"),
            ),
        )
        if state.get("plan_id"):
            conn.execute(
                "UPDATE production_plans SET status = 'produced' WHERE id = ?", (state["plan_id"],)
            )
    return {"new_stock": row["stock_qty"]}


def _summary_facts(state: MfgState) -> dict:
    return {
        "product": state["product"]["name"],
        "produced_qty": state["quantity"],
        "unit": state["product"]["unit"],
        "input_cost": state["input_cost"],
        "new_stock_level": state["new_stock"],
    }


def _narrate(state: MfgState) -> MfgState:
    model = get_chat_model(max_tokens=280)
    system = (
        "You are a manufacturing operations agent. In 2-3 sentences, confirm the production "
        "run and flag one operational watch-item (quality, throughput, or inventory)."
    )
    try:
        text = invoke_text(model, system, json.dumps(_summary_facts(state), indent=2))
        return {"narrative": text, "source": "claude"}
    except Exception:
        return {"narrative": _template(state), "source": "fallback"}


def _template_node(state: MfgState) -> MfgState:
    return {"narrative": _template(state), "source": "fallback"}


def _template(state: MfgState) -> str:
    f = _summary_facts(state)
    return (
        f"Produced {f['produced_qty']:g} {f['unit']} of {f['product']}; input cost {f['input_cost']} "
        f"booked as a purchase. Stock is now {f['new_stock_level']:g} {f['unit']}. "
        "Watch-item: verify batch QA before releasing to the storefront."
    )


def _route(state: MfgState) -> str:
    return "narrate" if get_chat_model() else "template"


def _build_graph():
    g = StateGraph(MfgState)
    g.add_node("resolve", _resolve)
    g.add_node("produce", _produce)
    g.add_node("narrate", _narrate)
    g.add_node("template", _template_node)
    g.set_entry_point("resolve")
    g.add_edge("resolve", "produce")
    g.add_conditional_edges("produce", _route, {"narrate": "narrate", "template": "template"})
    g.add_edge("narrate", END)
    g.add_edge("template", END)
    return g.compile()


class ManufacturingAgent(Agent):
    name = "manufacturing"
    title = "Manufacturing Agent"
    description = "Executes a production run: adds finished goods to stock and books the input cost."
    framework = "langgraph"

    def __init__(self):
        self._graph = _build_graph()

    def handle(self, payload: dict) -> dict:
        final = self._graph.invoke(
            {
                "plan_id": payload.get("plan_id"),
                "product_id": payload.get("product_id"),
                "quantity": float(payload.get("quantity") or 0) if payload.get("quantity") else 0,
            }
        )
        return {
            "product": final["product"]["name"],
            "produced_qty": final["quantity"],
            "unit": final["product"]["unit"],
            "input_cost": final["input_cost"],
            "new_stock_level": final["new_stock"],
            "narrative": final["narrative"],
            "reasoning_source": final["source"],
        }
