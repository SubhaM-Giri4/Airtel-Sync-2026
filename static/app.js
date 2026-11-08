const state = { profile: null, quote: null, order: null, toastTimer: null };
const currency = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const $ = (selector) => document.querySelector(selector);

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Something went wrong. Please try again.");
  return payload;
}

function money(amount) {
  return `₹${currency.format(amount)}`;
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
}

function setTab(tabName) {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === tabName));
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === tabName));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => setTab(tab.dataset.tab)));
document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => setTab(button.dataset.go)));

async function loadDashboard() {
  try {
    const data = await api("/api/dashboard");
    const cards = [
      ["Lead to activation", `${data.conversion_rate}%`, `${currency.format(data.activated_count)} of ${currency.format(data.lead_count)} leads`],
      ["Time to activate", `${data.average_days} days`, "Average for activated leads"],
      ["Cost to win a customer", money(data.acquisition_cost), "Average acquisition cost"],
      ["Status calls per customer", `${data.average_followups}`, `${data.churn_rate}% six-month churn in sample`],
    ];
    $("#metric-grid").innerHTML = cards.map(([label, value, note]) => `
      <article class="metric"><div class="metric-label">${label}</div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></article>`).join("");
    const max = Math.max(...data.stages.map((stage) => stage.count));
    $("#funnel").innerHTML = data.stages.map((stage) => `
      <div class="funnel-row"><span class="funnel-label">${stage.name}</span>
        <div class="funnel-track"><div class="funnel-bar" style="width:${Math.max(3, stage.count / max * 100)}%"></div></div>
        <span class="funnel-count">${currency.format(stage.count)}</span></div>`).join("");
  } catch (error) {
    $("#metric-grid").innerHTML = `<p class="error">Dashboard unavailable: ${error.message}</p>`;
  }
}

function renderQuote(quote) {
  const lines = quote.products.map((product) => `
    <div class="product-line">
      <div class="product-info"><strong>${product.name}${product.quantity > 1 ? ` × ${product.quantity}` : ""}</strong><small>${product.category} · ${product.unit}</small></div>
      <div class="product-cost">${money(product.monthly_min)}–${money(product.monthly_max)}<small>per month</small></div>
    </div>`).join("");
  const result = $("#recommendation");
  result.className = "card result-card";
  result.innerHTML = `
    <div class="quote-header"><div><p class="eyebrow">Eligible recommendation</p><h3>${quote.segment}</h3><p>${quote.profile.employees} employees · ${quote.profile.sites} site${quote.profile.sites === 1 ? "" : "s"} · Tier ${quote.profile.city_tier}</p></div>
      <div class="quote-price"><strong>${money(quote.monthly_min)}–${money(quote.monthly_max)}</strong><small>estimated / month</small></div></div>
    <div class="product-lines">${lines}</div>
    <div class="quote-summary"><span>One-time setup</span><strong>${money(quote.setup)}</strong></div>
    <div class="quote-summary"><span>Indicative installation</span><strong>Up to ${quote.install_days} days</strong></div>
    <div class="quote-explain">${quote.explanation}</div>
    <div class="quote-actions"><button class="button button-red" data-create-order>Continue to order <span>→</span></button><button class="text-link" data-copy-quote>Copy quote summary</button></div>
    <div class="result-assurance"><span>✓</span> Catalogue-backed pricing <span>·</span> No payment or commitment</div>`;
  $("#create-order").disabled = false;
  $("#order-hint").textContent = "This creates a temporary order reference only; it does not place a real order.";
  result.querySelector("[data-create-order]").addEventListener("click", createOrder);
  result.querySelector("[data-copy-quote]").addEventListener("click", async () => {
    const summary = `${quote.segment}: ${quote.products.map((item) => `${item.name} x${item.quantity}`).join(", ")}. ${money(quote.monthly_min)}–${money(quote.monthly_max)} per month; setup ${money(quote.setup)}.`;
    try {
      await navigator.clipboard.writeText(summary);
      showToast("Quote summary copied.");
    } catch {
      showToast("Copy is unavailable in this browser.");
    }
  });
}

$("#advisor-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorEl = $("#advisor-error");
  errorEl.textContent = "";
  const form = new FormData(event.currentTarget);
  state.profile = Object.fromEntries(form.entries());
  state.profile.city_tier = Number(state.profile.city_tier);
  state.profile.employees = Number(state.profile.employees);
  state.profile.sites = Number(state.profile.sites);
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  button.innerHTML = "Checking catalogue…";
  try {
    state.quote = await api("/api/recommend", { method: "POST", body: JSON.stringify(state.profile) });
    renderQuote(state.quote);
    showToast("Your eligible recommendation is ready.");
  } catch (error) {
    errorEl.textContent = error.message;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Build my recommendation <span>→</span>';
  }
});

function maskIdentifier(value, type) {
  const clean = value.toUpperCase();
  if (type === "gstin" && clean.length >= 6) return `${clean.slice(0, 2)}${"*".repeat(Math.max(0, clean.length - 6))}${clean.slice(-4)}`;
  if (type === "udyam" && clean.length >= 13) return `${clean.slice(0, 9)}${"*".repeat(Math.max(0, clean.length - 13))}${clean.slice(-4)}`;
  return "****";
}

$("#kyc-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorEl = $("#kyc-error");
  const result = $("#kyc-result");
  errorEl.textContent = "";
  result.className = "lookup-result";
  if (!$("#kyc-consent").checked) {
    errorEl.textContent = "Please give consent before the one-time lookup.";
    return;
  }
  const type = $("#registry-type").value;
  const identifier = $("#registry-id").value.trim();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  button.innerHTML = "Looking up…";
  try {
    const response = await api("/api/lookup", {
      method: "POST",
      body: JSON.stringify({ type, identifier, consent: true }),
    });
    const summary = response.found
      ? `<div class="lookup-fields"><div><span>Business</span><strong>${escapeHtml(response.business_name)}</strong></div><div><span>Masked ${type.toUpperCase()}</span><strong>${escapeHtml(response.masked_identifier)}</strong></div><div><span>${type === "gstin" ? "Status" : "Enterprise type"}</span><strong>${escapeHtml(type === "gstin" ? response.status : response.enterprise_type)}</strong></div><div><span>Location</span><strong>${escapeHtml(type === "gstin" ? response.state : `${response.city}, ${response.state}`)}</strong></div></div>`
      : `<div class="lookup-fields"><div><span>Masked ${type.toUpperCase()}</span><strong>${escapeHtml(response.masked_identifier)}</strong></div><div><span>Result</span><strong>${escapeHtml(response.message)}</strong></div></div>`;
    result.className = `lookup-result show${response.found ? "" : " not-found"}`;
    result.innerHTML = `<div class="lookup-top"><strong>${response.found ? "Registry match found" : "No match found"}</strong><span class="status-pill">${response.found ? "Synthetic match" : "Try another number"}</span></div>${summary}`;
    $("#registry-id").value = "";
  } catch (error) {
    errorEl.textContent = error.message;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Give consent & look up <span>→</span>';
  }
});

async function createOrder() {
  if (!state.profile) {
    setTab("advisor");
    showToast("Build a recommendation before creating an order.");
    return;
  }
  const button = $("#create-order");
  button.disabled = true;
  button.textContent = "Creating sample…";
  try {
    state.order = await api("/api/orders", { method: "POST", body: JSON.stringify(state.profile) });
    renderOrder(state.order);
    setTab("orders");
    showToast("Order reference created.");
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Continue to order <span>→</span>';
  }
}

$("#create-order").addEventListener("click", createOrder);

function renderOrder(order) {
  const result = $("#order-result");
  result.className = "card order-result";
  result.innerHTML = `
    <div class="order-top"><div><p class="eyebrow">Temporary sample order</p><div class="order-id">${escapeHtml(order.order_id)}</div></div><span class="order-status">${escapeHtml(order.status)}</span></div>
    <div class="order-meta"><div><span>Estimated activation</span><strong>${escapeHtml(order.expected_activation)} · up to ${order.install_days} days</strong></div><div><span>Monthly quote</span><strong>${money(order.monthly_min)}–${money(order.monthly_max)}</strong></div></div>
    <div class="timeline">${order.steps.map((step, index) => `<div class="timeline-step ${step.state}"><i class="timeline-dot"></i><div><strong>${escapeHtml(step.name)}</strong><small>${step.state === "complete" ? "Completed" : step.state === "next" ? "Next step · not submitted" : "Not started"}</small></div></div>`).join("")}</div>
    <p class="footnote">This reference exists only in the running server's memory. It does not reserve stock, initiate payment, or schedule installation.</p>`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

async function loadLeads() {
  try {
    const { leads } = await api("/api/leads");
    $("#lead-rows").innerHTML = leads.map((lead) => `
      <tr><td>${escapeHtml(lead.lead_id)}</td><td>${escapeHtml(lead.segment)}</td><td>${escapeHtml(lead.city)}</td>
      <td><span class="stage-pill">${escapeHtml(lead.stage)}</span></td><td class="score-cell">${lead.score}</td><td>${escapeHtml(lead.reason)}</td></tr>`).join("");
  } catch (error) {
    $("#lead-rows").innerHTML = `<tr><td colspan="6" class="loading-cell">Could not load sample leads: ${escapeHtml(error.message)}</td></tr>`;
  }
}

loadDashboard();
loadLeads();
