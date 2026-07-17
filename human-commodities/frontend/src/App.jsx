import React, { useEffect, useState, useCallback } from "react";
import { api } from "./api.js";

const TABS = ["Dashboard", "Catalog", "Agents", "Pipeline", "Storefront", "Outputs"];
const money = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");

export default function App() {
  const [tab, setTab] = useState("Dashboard");
  const [claude, setClaude] = useState(false);

  useEffect(() => {
    api.health().then((h) => setClaude(h.claude)).catch(() => {});
  }, []);

  return (
    <div className="app">
      <header className="top">
        <div className="logo">🏭</div>
        <div>
          <h1>Human Commodities</h1>
          <div className="sub">AI agents (LangGraph) that plan, research, produce & sell everyday goods</div>
        </div>
        <span className={"claude-badge" + (claude ? " on" : "")}>
          {claude ? "● Claude live" : "○ offline mode"}
        </span>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>

      {tab === "Dashboard" && <Dashboard />}
      {tab === "Catalog" && <Catalog />}
      {tab === "Agents" && <Agents />}
      {tab === "Pipeline" && <Pipeline />}
      {tab === "Storefront" && <Storefront />}
      {tab === "Outputs" && <Outputs />}
    </div>
  );
}

function Dashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { api.dashboard().then(setD).catch(() => {}); }, []);
  if (!d) return <p className="muted">Loading…</p>;
  const stats = [
    { label: "Products", value: d.products },
    { label: "Inventory value", value: money(d.inventory_value), accent: true },
    { label: "Orders", value: d.orders },
    { label: "Sales booked", value: money(d.total_sales), accent: true },
    { label: "Agent runs", value: d.agent_runs },
  ];
  return (
    <>
      <div className="grid cards">
        {stats.map((s) => (
          <div className="card stat" key={s.label}>
            <div className="label">{s.label}</div>
            <div className={"value" + (s.accent ? " accent" : "")}>{s.value}</div>
          </div>
        ))}
      </div>
      <div className="panel">
        <h2>How it works</h2>
        <p className="hint">
          Add commodities to your <b>Catalog</b>, let the <b>Planning</b> and <b>Research</b>{" "}
          agents advise you, sell through the <b>Storefront</b> (stock and accounting update
          automatically), and review everything the agents produced in <b>Outputs</b>.
          Manufacturing, Trading, Accounting, Business and Retail agents are stubbed for the
          next wave.
        </p>
      </div>
    </>
  );
}

function Catalog() {
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState({ name: "", category: "food", unit: "unit", cost_price: "", sell_price: "", stock_qty: "" });
  const [err, setErr] = useState("");

  const load = useCallback(() => api.products().then(setProducts).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      await api.createProduct({
        ...form,
        cost_price: Number(form.cost_price || 0),
        sell_price: Number(form.sell_price || 0),
        stock_qty: Number(form.stock_qty || 0),
      });
      setForm({ name: "", category: "food", unit: "unit", cost_price: "", sell_price: "", stock_qty: "" });
      load();
    } catch (e) { setErr(e.message); }
  };

  return (
    <div className="two-col">
      <div className="panel">
        <h2>Add commodity</h2>
        <p className="hint">The catalog defines your domain — anything humans need.</p>
        <form onSubmit={submit}>
          <div className="field"><label>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
          <div className="row">
            <div className="field"><label>Category</label>
              <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></div>
            <div className="field"><label>Unit</label>
              <input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} /></div>
          </div>
          <div className="row">
            <div className="field"><label>Cost price</label>
              <input type="number" step="0.01" value={form.cost_price} onChange={(e) => setForm({ ...form, cost_price: e.target.value })} /></div>
            <div className="field"><label>Sell price</label>
              <input type="number" step="0.01" value={form.sell_price} onChange={(e) => setForm({ ...form, sell_price: e.target.value })} /></div>
            <div className="field"><label>Stock</label>
              <input type="number" step="0.01" value={form.stock_qty} onChange={(e) => setForm({ ...form, stock_qty: e.target.value })} /></div>
          </div>
          {err && <p className="error">{err}</p>}
          <button className="btn" type="submit">Add to catalog</button>
        </form>
      </div>

      <div className="panel">
        <h2>Catalog ({products.length})</h2>
        <p className="hint">Live product data powers every agent and the storefront.</p>
        <table>
          <thead><tr><th>Product</th><th>Category</th><th>Cost</th><th>Sell</th><th>Stock</th><th></th></tr></thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td><span className="tag">{p.category}</span></td>
                <td>{money(p.cost_price)}</td>
                <td>{money(p.sell_price)}</td>
                <td>{p.stock_qty} {p.unit}</td>
                <td><button className="link" onClick={() => api.deleteProduct(p.id).then(load)}>delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Agents() {
  const [agents, setAgents] = useState([]);
  const [products, setProducts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [payload, setPayload] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.agents().then(setAgents).catch(() => {});
    api.products().then(setProducts).catch(() => {});
  }, []);

  const pick = (a) => {
    setSelected(a); setResult(null); setErr("");
    setPayload(a.name === "planning"
      ? { product_id: products[0]?.id, quantity: 100, target_days: 14 }
      : a.name === "research"
      ? { product_id: products[0]?.id, topic: "" }
      : a.name === "manufacturing"
      ? { product_id: products[0]?.id, quantity: 100 }
      : {});
  };

  const run = async () => {
    setBusy(true); setErr(""); setResult(null);
    try { setResult(await api.runAgent(selected.name, payload)); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="two-col">
      <div>
        <div className="grid" style={{ gap: 10 }}>
          {agents.map((a) => (
            <div key={a.name}
              className={"card agent-card" + (selected?.name === a.name ? " selected" : "")}
              onClick={() => pick(a)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <b>{a.title}</b>
                <span className={"tag " + (a.live ? "live" : "soon")}>{a.live ? `live · ${a.framework}` : "soon"}</span>
              </div>
              <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{a.description}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        {!selected && <p className="muted">Select an agent to run it.</p>}
        {selected && (
          <>
            <h2>{selected.title}</h2>
            <p className="hint">{selected.description}</p>

            {selected.name === "planning" && (
              <>
                <div className="field"><label>Product</label>
                  <select value={payload.product_id || ""} onChange={(e) => setPayload({ ...payload, product_id: Number(e.target.value) })}>
                    {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select></div>
                <div className="row">
                  <div className="field"><label>Quantity</label>
                    <input type="number" value={payload.quantity} onChange={(e) => setPayload({ ...payload, quantity: Number(e.target.value) })} /></div>
                  <div className="field"><label>Target days</label>
                    <input type="number" value={payload.target_days} onChange={(e) => setPayload({ ...payload, target_days: Number(e.target.value) })} /></div>
                </div>
              </>
            )}
            {selected.name === "research" && (
              <>
                <div className="field"><label>Product (optional)</label>
                  <select value={payload.product_id || ""} onChange={(e) => setPayload({ ...payload, product_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">— none —</option>
                    {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select></div>
                <div className="field"><label>Topic</label>
                  <input value={payload.topic || ""} placeholder="e.g. edible oils in South India"
                    onChange={(e) => setPayload({ ...payload, topic: e.target.value })} /></div>
              </>
            )}
            {selected.name === "manufacturing" && (
              <div className="row">
                <div className="field"><label>Product</label>
                  <select value={payload.product_id || ""} onChange={(e) => setPayload({ ...payload, product_id: Number(e.target.value) })}>
                    {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select></div>
                <div className="field"><label>Quantity to produce</label>
                  <input type="number" value={payload.quantity} onChange={(e) => setPayload({ ...payload, quantity: Number(e.target.value) })} /></div>
              </div>
            )}

            <button className="btn" onClick={run} disabled={busy || (!selected.live && false)}>
              {busy ? "Running…" : `Run ${selected.title}`}
            </button>
            {err && <p className="error">{err}</p>}
            {result && (
              <pre className="out">{typeof result.result === "string"
                ? result.result
                : JSON.stringify(result.result, null, 2)}</pre>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Pipeline() {
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState({ product_id: "", quantity: 200, target_days: 10 });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.products().then((p) => { setProducts(p); setForm((f) => ({ ...f, product_id: f.product_id || p[0]?.id })); });
  }, []);

  const run = async () => {
    setBusy(true); setErr(""); setRes(null);
    try {
      setRes(await api.orchestrate({
        product_id: Number(form.product_id),
        quantity: Number(form.quantity),
        target_days: Number(form.target_days),
      }));
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  };

  const r = res?.result;
  const stages = r && [
    { key: "research", icon: "🔬", title: "Research", body: r.research?.content?.slice(0, 260) + "…" },
    { key: "planning", icon: "🧮", title: "Planning",
      body: `Cost ${money(r.planning?.cost_estimate)} → revenue ${money(r.planning?.revenue_estimate)} · margin ${r.planning?.gross_margin_pct}% · plan #${r.planning?.plan_id}` },
    { key: "manufacturing", icon: "⚙️", title: "Manufacturing",
      body: `Produced ${r.manufacturing?.produced_qty} ${r.manufacturing?.unit} · new stock ${r.manufacturing?.new_stock_level} · input cost ${money(r.manufacturing?.input_cost)} booked` },
    { key: "accounting", icon: "📒", title: "Accounting (P&L)",
      body: `Revenue ${money(r.accounting?.revenue)} · COGS ${money(r.accounting?.cogs)} · net ${money(r.accounting?.net_profit)} — ${r.accounting?.narrative}` },
    { key: "trading", icon: "📈", title: "Trading (advisory)", body: r.trading?.narrative },
    { key: "retailer", icon: "🛍️", title: "Retailer", body: r.retailer?.narrative },
    { key: "business", icon: "🏢", title: "Business",
      body: `Sell-through ${r.business?.sell_through_pct}% · net ${money(r.business?.net_profit)} — ${r.business?.narrative}` },
  ];

  return (
    <>
      <div className="panel">
        <h2>Run the business end-to-end</h2>
        <p className="hint">
          One LangGraph orchestration graph hands a product through all seven agents:
          <b> Research → Planning → Manufacturing → Accounting → Trading → Retailer → Business</b>.
        </p>
        <div className="row" style={{ alignItems: "end" }}>
          <div className="field"><label>Product</label>
            <select value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })}>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></div>
          <div className="field"><label>Quantity</label>
            <input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></div>
          <div className="field"><label>Target days</label>
            <input type="number" value={form.target_days} onChange={(e) => setForm({ ...form, target_days: e.target.value })} /></div>
          <div className="field"><button className="btn" onClick={run} disabled={busy}>{busy ? "Running pipeline…" : "▶ Run pipeline"}</button></div>
        </div>
        {err && <p className="error">{err}</p>}
      </div>

      {stages && (
        <div className="panel">
          <h2>Pipeline result</h2>
          <div className="grid" style={{ gap: 12 }}>
            {stages.map((s, i) => (
              <div className="card" key={s.key}>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <span style={{ fontSize: 22 }}>{s.icon}</span>
                  <b>{i + 1}. {s.title}</b>
                  <span className="tag live" style={{ marginLeft: "auto" }}>done</span>
                </div>
                <div className="muted" style={{ fontSize: 13, marginTop: 8, lineHeight: 1.5 }}>{s.body}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function Storefront() {
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [form, setForm] = useState({ product_id: "", quantity: 1, customer_name: "" });
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    api.products().then((p) => { setProducts(p); setForm((f) => ({ ...f, product_id: f.product_id || p[0]?.id })); });
    api.orders().then(setOrders).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault(); setErr("");
    try {
      await api.createOrder({ ...form, product_id: Number(form.product_id), quantity: Number(form.quantity) });
      setForm({ ...form, quantity: 1, customer_name: "" });
      load();
    } catch (e) { setErr(e.message); }
  };

  return (
    <div className="two-col">
      <div className="panel">
        <h2>New order</h2>
        <p className="hint">Placing an order decrements stock and books a sale automatically.</p>
        <form onSubmit={submit}>
          <div className="field"><label>Product</label>
            <select value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })}>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name} — {money(p.sell_price)} ({p.stock_qty} left)</option>)}
            </select></div>
          <div className="row">
            <div className="field"><label>Quantity</label>
              <input type="number" min="1" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></div>
            <div className="field"><label>Customer</label>
              <input value={form.customer_name} placeholder="walk-in" onChange={(e) => setForm({ ...form, customer_name: e.target.value })} /></div>
          </div>
          {err && <p className="error">{err}</p>}
          <button className="btn" type="submit">Place order</button>
        </form>
      </div>
      <div className="panel">
        <h2>Orders ({orders.length})</h2>
        <table>
          <thead><tr><th>#</th><th>Product</th><th>Qty</th><th>Customer</th><th>Total</th></tr></thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td>{o.id}</td><td>{o.product_name || "—"}</td><td>{o.quantity}</td>
                <td>{o.customer_name}</td><td>{money(o.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Outputs() {
  const [plans, setPlans] = useState([]);
  const [reports, setReports] = useState([]);
  const [txns, setTxns] = useState([]);
  useEffect(() => {
    api.plans().then(setPlans).catch(() => {});
    api.reports().then(setReports).catch(() => {});
    api.transactions().then(setTxns).catch(() => {});
  }, []);
  return (
    <>
      <div className="panel">
        <h2>Production plans ({plans.length})</h2>
        <table>
          <thead><tr><th>#</th><th>Product</th><th>Qty</th><th>Status</th><th>When</th></tr></thead>
          <tbody>{plans.map((p) => (
            <tr key={p.id}><td>{p.id}</td><td>{p.product_name}</td><td>{p.quantity}</td>
              <td><span className="tag">{p.status}</span></td><td className="muted">{p.created_at}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="panel">
        <h2>Research reports ({reports.length})</h2>
        {reports.map((r) => (
          <details key={r.id} style={{ marginBottom: 8 }}>
            <summary style={{ cursor: "pointer" }}><b>{r.topic}</b> <span className="muted">— {r.created_at}</span></summary>
            <pre className="out">{r.content}</pre>
          </details>
        ))}
        {reports.length === 0 && <p className="muted">No reports yet — run the Research agent.</p>}
      </div>
      <div className="panel">
        <h2>Ledger ({txns.length})</h2>
        <table>
          <thead><tr><th>#</th><th>Kind</th><th>Amount</th><th>Description</th></tr></thead>
          <tbody>{txns.map((t) => (
            <tr key={t.id}><td>{t.id}</td><td><span className="tag">{t.kind}</span></td>
              <td>{money(t.amount)}</td><td>{t.description}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}
