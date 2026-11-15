/* Hifazat — frontend application logic. */
(() => {
  const $ = (id) => document.getElementById(id);
  let currentUser = null;
  let activeView = "dashboard";
  let ws = null;

  const fmtPKR = (n) => "Rs " + Number(n || 0).toLocaleString("en-PK", { maximumFractionDigits: 0 });

  const dateShort = (iso) => {
    const d = new Date(iso);
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }) + " " +
      d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  };

  const sevClass = (sev) => "sev-" + (sev || "low");

  // ── auth screen ────────────────────────
  const switchTab = (tab) => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
    $("name-field").classList.toggle("hidden", tab !== "register");
    $("auth-submit").textContent = tab === "register" ? "Create account" : "Sign in";
  };

  document.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => switchTab(t.dataset.tab))
  );

  $("auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = $("auth-email").value.trim();
    const password = $("auth-password").value;
    const isRegister = !$("name-field").classList.contains("hidden");
    const name = $("auth-name").value.trim();
    $("auth-error").classList.add("hidden");
    try {
      let result;
      if (isRegister) result = await API.register(email, name, password);
      else result = await API.login(email, password);
      API.setToken(result.token.access_token);
      currentUser = result.token.user;
      enterApp();
    } catch (err) {
      $("auth-error").textContent = err.message;
      $("auth-error").classList.remove("hidden");
    }
  });

  $("logout-btn").addEventListener("click", () => {
    API.setToken(null);
    location.reload();
  });

  document.addEventListener("hf:logout", () => {
    API.setToken(null);
    location.reload();
  });

  // ── navigation ─────────────────────────
  document.querySelectorAll(".nav-btn").forEach((btn) =>
    btn.addEventListener("click", () => showView(btn.dataset.view))
  );

  const showView = (view) => {
    activeView = view;
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
    ["dashboard", "transactions", "alerts", "insights"].forEach((v) => {
      $(v + "-view").classList.toggle("hidden", v !== view);
    });
    if (view === "dashboard") loadDashboard();
    if (view === "transactions") loadTransactions();
    if (view === "alerts") loadAlerts();
    if (view === "insights") loadInsights();
  };

  // ── enter / leave ──────────────────────
  const enterApp = async () => {
    $("auth-view").classList.add("hidden");
    $("app-view").classList.remove("hidden");
    $("user-name").textContent = currentUser?.name?.split(" ")[0] || "friend";
    connectWS();
    showView("dashboard");
  };

  const connectWS = () => {
    ws = API.ws();
    if (!ws) return;
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "new_alert") {
          toast("⚠ Alert: " + msg.alert.summary);
          loadDashboard();
        }
      } catch (_) {}
    };
    ws.onclose = () => setTimeout(connectWS, 4000); // reconnect loop
  };

  const toast = (text) => {
    const el = $("toast");
    el.textContent = text;
    el.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hidden"), 4200);
  };

  // ── renderers ──────────────────────────
  const txRow = (tx) => `
    <li>
      <div class="tx-main">
        <div class="tx-merchant">${esc(tx.merchant || tx.category || "Transaction")}</div>
        <div class="tx-meta">${dateShort(tx.occurred_at)} · ${esc(tx.city || "—")}${tx.is_flagged ? " · <span class='warn'>flagged</span>" : ""}</div>
      </div>
      <div class="tx-amount neg">${fmtPKR(tx.amount)}</div>
    </li>`;

  const alertRow = (al) => `
    <li>
      <div class="tx-main">
        <div class="tx-merchant"><span class="sev ${sevClass(al.severity)}">${esc(al.severity)}</span> ${esc(al.summary)}</div>
        <div class="tx-meta">${dateShort(al.created_at)} · <span class="score-chip">score <b>${al.score}</b>/100</span>
          ${al.status !== "open" ? ` <span class="status-pill ${al.status}">${esc(al.status)}${al.outcome ? " · " + esc(al.outcome) : ""}</span>` : ""}
        </div>
      </div>
      <div class="alert-actions">
        <button class="btn-ghost btn-sm" data-reasons='${JSON.stringify(al.reasons).replace(/'/g, "&#39;")}'>Why</button>
        ${al.status !== "resolved" ? `<button class="btn-ghost btn-sm" data-ack="${al.id}">Ack</button>
        <button class="btn-ghost btn-sm" data-resolve="${al.id}" data-outcome="confirmed_fraud">Fraud</button>
        <button class="btn-ghost btn-sm" data-resolve="${al.id}" data-outcome="false_positive">OK</button>` : ""}
      </div>
    </li>`;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ── dashboard ───────────────────────────
  const loadDashboard = async () => {
    try {
      const [accts, txs, alertList, stats] = await Promise.all([
        API.accounts(), API.transactions(8), API.alerts("open"), API.alertStats(),
      ]);
      const balance = accts.reduce((s, a) => s + a.balance, 0);
      $("kpi-balance").textContent = fmtPKR(balance);
      $("kpi-alerts").textContent = stats.open;
      $("kpi-alerts").className = "kpi-value" + (stats.open ? " warn" : " ok");
      $("kpi-risk").textContent = fmtPKR(stats.at_risk_amount);
      $("kpi-flagrate").textContent = (alertList.length ? txs.filter((t) => t.is_flagged).length : 0) + "/" + txs.length;
      $("recent-list").innerHTML = txs.length ? txs.map(txRow).join("") : "<li class='muted'>No transactions yet.</li>";
      $("latest-alerts").innerHTML = alertList.length ? alertList.slice(0, 5).map(alertRow).join("") : "<li class='muted'>No open alerts 🎉</li>";
      const badge = $("alert-badge");
      badge.textContent = stats.open;
      badge.classList.toggle("hidden", !stats.open);
      bindAlertActions();
    } catch (err) {
      toast(err.message);
    }
  };

  // ── transactions ───────────────────────
  const loadTransactions = async () => {
    try {
      const txs = await API.transactions(100);
      $("tx-list").innerHTML = txs.length ? txs.map(txRow).join("") : "<li class='muted'>Nothing yet.</li>";
    } catch (err) {
      toast(err.message);
    }
  };

  // ── alerts ─────────────────────────────
  const loadAlerts = async () => {
    try {
      const [all, stats] = await Promise.all([API.alerts(), API.alertStats()]);
      $("stat-open").textContent = stats.open;
      $("stat-ack").textContent = stats.acknowledged;
      $("stat-resolved").textContent = stats.resolved;
      $("stat-fraud").textContent = stats.confirmed_fraud;
      $("alert-list").innerHTML = all.length ? all.map(alertRow).join("") : "<li class='muted'>No alerts — clean bill of health.</li>";
      bindAlertActions();
    } catch (err) {
      toast(err.message);
    }
  };

  const bindAlertActions = () => {
    document.querySelectorAll("[data-reasons]").forEach((b) =>
      b.addEventListener("click", () => showReasons(JSON.parse(b.dataset.reasons))));
    document.querySelectorAll("[data-ack]").forEach((b) =>
      b.addEventListener("click", async () => {
        try { await API.alertAction(b.dataset.ack, "acknowledge"); loadAlerts(); } catch (e) { toast(e.message); }
      }));
    document.querySelectorAll("[data-resolve]").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          await API.alertAction(b.dataset.resolve, "resolve", b.dataset.outcome);
          toast(b.dataset.outcome === "confirmed_fraud" ? "Marked as fraud — good catch." : "Marked as a false positive.");
          loadAlerts();
        } catch (e) { toast(e.message); }
      }));
  };

  const showReasons = (reasons) => {
    const body = $("reason-body");
    body.innerHTML = (reasons.length ? reasons : [{ label: "No specific rule", detail: "Transaction scored below alert threshold.", severity: 0 }])
      .map((r) => `
        <div class="reason-row">
          <div class="reason-label">${esc(r.label)} <span class="reason-weight">· weight ${r.weight}</span></div>
          <div class="reason-detail">${esc(r.detail)}</div>
        </div>`).join("");
    $("reason-modal").classList.remove("hidden");
  };

  $("reason-close").addEventListener("click", () => $("reason-modal").classList.add("hidden"));

  // ── insights ───────────────────────────
  const loadInsights = async () => {
    try {
      const ins = await API.insights();
      $("ins-week").textContent = fmtPKR(ins.total_spent);
      $("ins-change").textContent = (ins.change_pct >= 0 ? "+" : "") + ins.change_pct + "%";
      $("ins-change").className = "kpi-value " + (ins.change_pct > 10 ? "warn" : "ok");
      $("ins-avg").textContent = fmtPKR(ins.avg_tx);
      $("ins-top").textContent = esc(ins.top_category || "—");
      $("category-bars").innerHTML = ins.by_category.length
        ? ins.by_category.map((c) => `
            <div class="bar-row">
              <span class="bar-label">${esc(c.category)}</span>
              <div class="bar-track"><div class="bar-fill" style="width:${Math.max(4, c.share * 100)}%"></div></div>
              <span class="bar-pct">${Math.round(c.share * 100)}%</span>
            </div>`).join("")
        : "<p class='muted'>Not enough data yet.</p>";
      $("recurring-list").innerHTML = (ins.recurring_merchants || []).length
        ? ins.recurring_merchants.map((r) => `
            <li>
              <div class="tx-main">
                <div class="tx-merchant">${esc(r.merchant)}</div>
                <div class="tx-meta">${r.count} tx · last ${dateShort(r.last)}</div>
              </div>
              <div class="tx-amount">${fmtPKR(r.avg_amount)}</div>
            </li>`).join("")
        : "<li class='muted'>No recurring merchants detected yet.</li>";
    } catch (err) {
      toast(err.message);
    }
  };

  // ── new transaction modal ──────────────
  $("open-new-tx").addEventListener("click", () => $("tx-modal").classList.remove("hidden"));
  $("tx-cancel").addEventListener("click", () => $("tx-modal").classList.add("hidden"));

  $("tx-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const accts = await API.accounts();
      const accountId = accts[0]?.id;
      if (!accountId) { toast("Create an account first."); return; }
      const tx = await API.createTransaction(accountId, {
        amount: parseFloat($("tx-amount").value),
        merchant: $("tx-merchant").value.trim() || "Manual entry",
        category: $("tx-category").value,
        city: $("tx-city").value.trim() || "Karachi",
        country: $("tx-country").value.trim() || "Pakistan",
        channel: $("tx-channel").value,
      });
      $("tx-modal").classList.add("hidden");
      e.target.reset();
      toast(tx.is_flagged ? `⚠ Flagged (score ${tx.risk_score}/100) — see Alerts.` : "Transaction added. No flags.");
      showView("dashboard");
    } catch (err) {
      toast(err.message);
    }
  });

  // ── boot ───────────────────────────────
  API.restore();
  if (API.token) {
    API.me()
      .then((u) => { currentUser = u; enterApp(); })
      .catch(() => { /* hf:logout already fired */ });
  }
})();
