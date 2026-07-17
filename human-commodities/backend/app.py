"""Human Commodities platform — Flask REST API.

An AI-agent-driven backend for producing and selling human-needs commodities.
Domain-agnostic: the product catalog defines what you make and sell.
"""
import os

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from db import init_db, get_conn, rows_to_dicts
from agents.registry import list_agents, get_agent
from agents.orchestrator import run_flow, STAGES
from agents.llm import CLAUDE_AVAILABLE

app = Flask(__name__)
CORS(app)

LANDING_DIR = os.path.join(os.path.dirname(__file__), "..", "landing")
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")


# --------------------------------------------------------------------------- #
#  Meta
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return jsonify(status="ok", claude=CLAUDE_AVAILABLE, framework="langgraph")


@app.get("/api/dashboard")
def dashboard():
    with get_conn() as conn:
        products = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(stock_qty*sell_price),0) v FROM products").fetchone()
        orders = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(total),0) v FROM orders").fetchone()
        sales = conn.execute("SELECT COALESCE(SUM(amount),0) v FROM transactions WHERE kind='sale'").fetchone()
        runs = conn.execute("SELECT COUNT(*) c FROM agent_runs").fetchone()
    return jsonify(
        products=products["c"],
        inventory_value=round(products["v"], 2),
        orders=orders["c"],
        order_revenue=round(orders["v"], 2),
        total_sales=round(sales["v"], 2),
        agent_runs=runs["c"],
    )


# --------------------------------------------------------------------------- #
#  Products (the data-driven "domain")
# --------------------------------------------------------------------------- #
@app.get("/api/products")
def list_products():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return jsonify(rows_to_dicts(rows))


@app.post("/api/products")
def create_product():
    d = request.get_json(force=True) or {}
    if not d.get("name"):
        return jsonify(error="name is required"), 400
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO products (name, category, unit, description, cost_price, sell_price, stock_qty)
               VALUES (?,?,?,?,?,?,?)""",
            (
                d["name"],
                d.get("category", "general"),
                d.get("unit", "unit"),
                d.get("description", ""),
                float(d.get("cost_price", 0)),
                float(d.get("sell_price", 0)),
                float(d.get("stock_qty", 0)),
            ),
        )
        pid = cur.lastrowid
        row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    return jsonify(dict(row)), 201


@app.put("/api/products/<int:pid>")
def update_product(pid):
    d = request.get_json(force=True) or {}
    fields = ["name", "category", "unit", "description", "cost_price", "sell_price", "stock_qty"]
    sets = [f"{f}=?" for f in fields if f in d]
    if not sets:
        return jsonify(error="no fields to update"), 400
    vals = [d[f] for f in fields if f in d] + [pid]
    with get_conn() as conn:
        conn.execute(f"UPDATE products SET {', '.join(sets)} WHERE id=?", vals)
        row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not row:
        return jsonify(error="not found"), 404
    return jsonify(dict(row))


@app.delete("/api/products/<int:pid>")
def delete_product(pid):
    with get_conn() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
    return jsonify(deleted=pid)


# --------------------------------------------------------------------------- #
#  Agents
# --------------------------------------------------------------------------- #
@app.get("/api/agents")
def agents_index():
    return jsonify(list_agents())


@app.post("/api/agents/<name>/run")
def run_agent(name):
    agent = get_agent(name)
    if not agent:
        return jsonify(error=f"unknown agent '{name}'"), 404
    payload = request.get_json(force=True, silent=True) or {}
    return jsonify(agent.run(payload))


@app.post("/api/orchestrate")
def orchestrate():
    """Run the full business loop for a product: research → plan → produce → P&L."""
    d = request.get_json(force=True) or {}
    product_id = d.get("product_id")
    quantity = float(d.get("quantity") or 0)
    target_days = int(d.get("target_days") or 14)
    if not product_id or quantity <= 0:
        return jsonify(error="product_id and positive quantity required"), 400
    try:
        result = run_flow(product_id, quantity, target_days)
    except Exception as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(stages=STAGES, result=result)


@app.get("/api/agent-runs")
def agent_runs():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM agent_runs ORDER BY id DESC LIMIT 50").fetchall()
    return jsonify(rows_to_dicts(rows))


# --------------------------------------------------------------------------- #
#  Agent outputs
# --------------------------------------------------------------------------- #
@app.get("/api/plans")
def list_plans():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.*, pr.name AS product_name
               FROM production_plans p LEFT JOIN products pr ON pr.id=p.product_id
               ORDER BY p.id DESC"""
        ).fetchall()
    return jsonify(rows_to_dicts(rows))


@app.get("/api/reports")
def list_reports():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM research_reports ORDER BY id DESC").fetchall()
    return jsonify(rows_to_dicts(rows))


# --------------------------------------------------------------------------- #
#  Orders + accounting (basic retail loop)
# --------------------------------------------------------------------------- #
@app.get("/api/orders")
def list_orders():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT o.*, pr.name AS product_name
               FROM orders o LEFT JOIN products pr ON pr.id=o.product_id
               ORDER BY o.id DESC"""
        ).fetchall()
    return jsonify(rows_to_dicts(rows))


@app.post("/api/orders")
def create_order():
    d = request.get_json(force=True) or {}
    product_id = d.get("product_id")
    qty = float(d.get("quantity") or 0)
    if not product_id or qty <= 0:
        return jsonify(error="product_id and positive quantity required"), 400
    with get_conn() as conn:
        prod = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not prod:
            return jsonify(error="product not found"), 404
        if prod["stock_qty"] < qty:
            return jsonify(error=f"insufficient stock ({prod['stock_qty']} available)"), 400
        total = round(prod["sell_price"] * qty, 2)
        cur = conn.execute(
            "INSERT INTO orders (product_id, quantity, customer_name, total, status) VALUES (?,?,?,?,?)",
            (product_id, qty, d.get("customer_name", "walk-in"), total, "placed"),
        )
        oid = cur.lastrowid
        conn.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id=?", (qty, product_id))
        conn.execute(
            "INSERT INTO transactions (kind, amount, description, ref_id) VALUES ('sale',?,?,?)",
            (total, f"Order #{oid}: {qty:g} x {prod['name']}", oid),
        )
        row = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    return jsonify(dict(row)), 201


@app.get("/api/transactions")
def list_transactions():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT 100").fetchall()
    return jsonify(rows_to_dicts(rows))


# --------------------------------------------------------------------------- #
#  Landing page (optional static serve)
# --------------------------------------------------------------------------- #
@app.get("/")
def landing():
    return send_from_directory(LANDING_DIR, "index.html")


# Serve the built React console (single-deployable). Run `npm run build` first.
@app.get("/app")
@app.get("/app/")
def console():
    if not os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        return (
            "<h1>Console not built</h1><p>Run <code>npm run build</code> in "
            "<code>frontend/</code>, or use the dev server at "
            "<a href='http://localhost:5173'>localhost:5173</a>.</p>",
            503,
        )
    return send_from_directory(FRONTEND_DIST, "index.html")


@app.get("/app/<path:path>")
def console_assets(path):
    full = os.path.join(FRONTEND_DIST, path)
    if os.path.isfile(full):
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, "index.html")  # SPA fallback


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("HC_PORT", 5060))
    app.run(host="127.0.0.1", port=port, debug=True)
