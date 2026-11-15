/* Hifazat — API client wrapper. */
const API = {
  token: null,
  user: null,

  get base() {
    return window.location.origin;
  },

  setToken(t) {
    this.token = t;
    if (t) localStorage.setItem("hf_token", t);
    else localStorage.removeItem("hf_token");
  },

  restore() {
    this.token = localStorage.getItem("hf_token");
  },

  async request(path, opts = {}) {
    const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    const res = await fetch(this.base + path, { ...opts, headers });
    if (res.status === 401) {
      this.setToken(null);
      document.dispatchEvent(new CustomEvent("hf:logout"));
      throw new Error("Session expired");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
    return data;
  },

  login(email, password) {
    return this.request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  register(email, name, password) {
    return this.request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, name, password }),
    });
  },

  me() {
    return this.request("/api/auth/me");
  },

  accounts() {
    return this.request("/api/accounts");
  },

  transactions(limit = 50) {
    return this.request(`/api/transactions?limit=${limit}`);
  },

  createTransaction(accountId, payload) {
    return this.request(`/api/accounts/${accountId}/transactions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  alerts(status) {
    const q = status ? `?status=${status}` : "";
    return this.request(`/api/alerts${q}`);
  },

  alertStats() {
    return this.request("/api/alerts/stats");
  },

  alertAction(id, action, outcome) {
    return this.request(`/api/alerts/${id}/action`, {
      method: "POST",
      body: JSON.stringify({ action, outcome }),
    });
  },

  insights() {
    return this.request("/api/insights");
  },

  ws() {
    if (!this.token) return null;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return new WebSocket(`${proto}://${location.host}/ws/alerts?token=${encodeURIComponent(this.token)}`);
  },
};
