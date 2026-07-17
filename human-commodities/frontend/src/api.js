const BASE = "/api";

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

export const api = {
  health: () => req("/health"),
  dashboard: () => req("/dashboard"),
  products: () => req("/products"),
  createProduct: (p) => req("/products", { method: "POST", body: JSON.stringify(p) }),
  deleteProduct: (id) => req(`/products/${id}`, { method: "DELETE" }),
  agents: () => req("/agents"),
  runAgent: (name, payload) =>
    req(`/agents/${name}/run`, { method: "POST", body: JSON.stringify(payload) }),
  orchestrate: (payload) =>
    req("/orchestrate", { method: "POST", body: JSON.stringify(payload) }),
  plans: () => req("/plans"),
  reports: () => req("/reports"),
  orders: () => req("/orders"),
  createOrder: (o) => req("/orders", { method: "POST", body: JSON.stringify(o) }),
  transactions: () => req("/transactions"),
};
