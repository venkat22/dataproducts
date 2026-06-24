const api = (path, opts) => fetch(`/api${path}`, opts).then(async (r) => {
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${r.status})`);
  }
  return r.status === 204 ? null : r.json();
});

const $ = (sel) => document.querySelector(sel);
const FIELD_KEYS = [
  "name", "description", "domain", "owner_name", "owner_email",
  "classification", "source_systems", "update_frequency",
  "output_format", "sla", "tags",
];

let allProducts = [];
let OPTIONS = { field_types: [], rule_types: [], contract_statuses: [] };

// ---- Tabs / views -----------------------------------------------------------
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchView(tab.dataset.view));
});
function switchView(view) {
  // The contract view is reached from a catalog item, not a top tab; keep the
  // active tab highlight on Catalog while it's open.
  const activeTab = view === "contract" ? "catalog" : view;
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.view === activeTab));
  $("#view-register").classList.toggle("hidden", view !== "register");
  $("#view-catalog").classList.toggle("hidden", view !== "catalog");
  $("#view-contract").classList.toggle("hidden", view !== "contract");
  if (view === "catalog") loadCatalog();
}

// ---- Toast ------------------------------------------------------------------
let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2600);
}

// ---- Bootstrap options + health --------------------------------------------
async function bootstrap() {
  try {
    const opts = await api("/options");
    OPTIONS = opts;
    fillSelect("#classification", opts.classifications);
    fillSelect("#update_frequency", opts.frequencies);
    fillSelect("#output_format", opts.formats);
    fillSelect("#c-status", opts.contract_statuses);
  } catch (e) { /* selects stay empty; non-fatal */ }

  try {
    const health = await api("/health");
    const label = health.ai_enabled ? "Claude connected" : "local mode";
    const cls = health.ai_enabled ? "on" : "off";
    ["#ai-status", "#ai-status-c"].forEach((sel) => {
      const pill = $(sel);
      if (pill) { pill.textContent = label; pill.classList.add(cls); }
    });
  } catch (e) {
    ["#ai-status", "#ai-status-c"].forEach((sel) => {
      if ($(sel)) $(sel).textContent = "offline";
    });
  }
  loadCatalog();
}

function fillSelect(sel, values) {
  const el = $(sel);
  el.innerHTML = "";
  values.forEach((v) => {
    const o = document.createElement("option");
    o.value = v; o.textContent = v;
    el.appendChild(o);
  });
}

// ---- AI assist --------------------------------------------------------------
$("#ai-fill").addEventListener("click", async () => {
  const prompt = $("#ai-prompt").value.trim();
  const note = $("#ai-note");
  if (!prompt) { note.textContent = "Type a description first."; return; }
  const btn = $("#ai-fill");
  btn.disabled = true; btn.textContent = "Thinking…";
  note.textContent = "";
  try {
    const res = await api("/assist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    applyFields(res.fields);
    note.textContent = (res.source === "claude" ? "✓ Filled by Claude. " : "✓ Filled locally. ")
      + (res.note || "Review and edit before saving.");
    toast("Form pre-filled — review the details");
  } catch (e) {
    note.textContent = "Assistant error: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = "Help me fill the form";
  }
});

function applyFields(fields) {
  FIELD_KEYS.forEach((k) => {
    if (k in fields && $("#" + k)) {
      $("#" + k).value = fields[k] ?? "";
      flash($("#" + k));
    }
  });
  if ("contains_pii" in fields) {
    $("#contains_pii").checked = !!fields.contains_pii;
    flash($("#contains_pii").closest(".checkbox"));
  }
}
function flash(el) {
  if (!el) return;
  el.classList.remove("flash");
  void el.offsetWidth;
  el.classList.add("flash");
}

// ---- Form save / reset ------------------------------------------------------
$("#dp-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#form-msg");
  msg.textContent = ""; msg.className = "form-msg";
  const payload = collectForm();
  if (!payload.name) {
    msg.textContent = "Name is required."; msg.classList.add("err"); return;
  }
  const id = $("#product_id").value;
  try {
    if (id) {
      await api(`/data-products/${id}`, jsonReq("PUT", payload));
      toast("Data product updated");
    } else {
      await api("/data-products", jsonReq("POST", payload));
      toast("Data product registered");
    }
    resetForm();
    switchView("catalog");
  } catch (err) {
    msg.textContent = err.message; msg.classList.add("err");
  }
});

const jsonReq = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function collectForm() {
  const data = {};
  FIELD_KEYS.forEach((k) => { data[k] = $("#" + k)?.value ?? ""; });
  data.contains_pii = $("#contains_pii").checked;
  return data;
}

$("#form-reset").addEventListener("click", resetForm);
function resetForm() {
  $("#dp-form").reset();
  $("#product_id").value = "";
  $("#form-title").textContent = "Register a Data Product";
  $("#form-msg").textContent = "";
}

function editProduct(p) {
  applyFields(p);
  $("#product_id").value = p.id;
  $("#form-title").textContent = `Edit: ${p.name}`;
  switchView("register");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function deleteProduct(id, name) {
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  try {
    await api(`/data-products/${id}`, { method: "DELETE" });
    toast("Deleted");
    loadCatalog();
  } catch (e) { toast("Delete failed: " + e.message); }
}

// ---- Catalog ----------------------------------------------------------------
async function loadCatalog() {
  try {
    allProducts = await api("/data-products");
    $("#catalog-count").textContent = allProducts.length;
    renderCatalog($("#search").value);
  } catch (e) {
    $("#catalog-list").innerHTML = `<p class="empty">Could not load catalog: ${e.message}</p>`;
  }
}

$("#search").addEventListener("input", (e) => renderCatalog(e.target.value));

function renderCatalog(query = "") {
  const q = query.trim().toLowerCase();
  const list = $("#catalog-list");
  const items = allProducts.filter((p) =>
    !q || [p.name, p.description, p.domain, p.tags, p.owner_name]
      .join(" ").toLowerCase().includes(q));

  if (!items.length) {
    list.innerHTML = `<p class="empty">${allProducts.length
      ? "No data products match your search."
      : "No data products registered yet. Head to the Register tab to add one."}</p>`;
    return;
  }

  list.innerHTML = items.map((p) => `
    <div class="dp">
      <div class="dp-head">
        <div>
          <h3 class="dp-title">${esc(p.name)}</h3>
          <p class="dp-desc">${esc(p.description) || "<em>No description</em>"}</p>
        </div>
        <div class="dp-actions">
          <button class="btn ghost small" data-contract="${p.id}">${p.has_contract ? "Contract" : "+ Contract"}</button>
          <button class="btn ghost small" data-edit="${p.id}">Edit</button>
          <button class="btn danger small" data-del="${p.id}">Delete</button>
        </div>
      </div>
      <div class="chips">
        ${p.domain ? `<span class="chip">${esc(p.domain)}</span>` : ""}
        <span class="chip cls-${esc(p.classification)}">${esc(p.classification)}</span>
        <span class="chip">${esc(p.output_format)}</span>
        <span class="chip">${esc(p.update_frequency)}</span>
        ${p.contains_pii ? `<span class="chip pii">PII</span>` : ""}
        <span class="chip ${p.has_contract ? "contract" : "nocontract"}">${p.has_contract ? "✓ Contract" : "No contract"}</span>
        ${tagChips(p.tags)}
      </div>
      <div class="dp-meta">
        ${p.owner_name ? `<b>${esc(p.owner_name)}</b>` : ""}
        ${p.owner_email ? ` · ${esc(p.owner_email)}` : ""}
        ${p.source_systems ? ` · Sources: ${esc(p.source_systems)}` : ""}
        ${p.sla ? ` · SLA: ${esc(p.sla)}` : ""}
      </div>
    </div>
  `).join("");

  list.querySelectorAll("[data-edit]").forEach((b) =>
    b.addEventListener("click", () =>
      editProduct(allProducts.find((p) => p.id == b.dataset.edit))));
  list.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => {
      const p = allProducts.find((x) => x.id == b.dataset.del);
      deleteProduct(p.id, p.name);
    }));
  list.querySelectorAll("[data-contract]").forEach((b) =>
    b.addEventListener("click", () =>
      openContract(allProducts.find((p) => p.id == b.dataset.contract))));
}

function tagChips(tags) {
  if (!tags) return "";
  return tags.split(",").map((t) => t.trim()).filter(Boolean)
    .map((t) => `<span class="chip">#${esc(t)}</span>`).join("");
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---- Data contracts ---------------------------------------------------------
let currentProduct = null;

async function openContract(product) {
  if (!product) return;
  currentProduct = product;
  $("#contract-product-id").value = product.id;
  $("#contract-product").innerHTML =
    `Contract for <b>${esc(product.name)}</b>`;
  $("#contract-msg").textContent = "";
  $("#ai-note-c").textContent = "";
  $("#ai-prompt-c").value = "";

  let contract = blankContract();
  let exists = false;
  if (product.has_contract) {
    try { contract = await api(`/data-products/${product.id}/contract`); exists = true; }
    catch (e) { /* fall back to blank */ }
  }
  fillContract(contract);
  $("#contract-title").textContent = exists ? "Edit Data Contract" : "New Data Contract";
  $("#contract-delete").classList.toggle("hidden", !exists);
  switchView("contract");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function blankContract() {
  return {
    version: "1.0.0", status: "draft",
    schema_fields: [], quality_rules: [],
    slo_availability: "", slo_freshness: "", slo_max_latency: "",
  };
}

function fillContract(c) {
  $("#c-version").value = c.version || "1.0.0";
  $("#c-status").value = c.status || "draft";
  $("#c-availability").value = c.slo_availability || "";
  $("#c-freshness").value = c.slo_freshness || "";
  $("#c-latency").value = c.slo_max_latency || "";
  renderSchemaRows(c.schema_fields || []);
  renderRuleRows(c.quality_rules || []);
}

function optionsHtml(values, selected) {
  return values.map((v) =>
    `<option value="${esc(v)}" ${v === selected ? "selected" : ""}>${esc(v)}</option>`).join("");
}

function renderSchemaRows(fields) {
  const box = $("#schema-rows");
  if (!fields.length) {
    box.innerHTML = `<p class="empty-rows">No fields yet — add one or use the assistant.</p>`;
    return;
  }
  box.innerHTML = fields.map((f) => `
    <div class="schema-row">
      <input class="f-name" value="${esc(f.name)}" placeholder="field_name" />
      <select class="f-type">${optionsHtml(OPTIONS.field_types, f.type || "string")}</select>
      <span class="cell-check"><input type="checkbox" class="f-req" ${f.required ? "checked" : ""} /></span>
      <span class="cell-check"><input type="checkbox" class="f-pii" ${f.pii ? "checked" : ""} /></span>
      <input class="f-desc" value="${esc(f.description)}" placeholder="description" />
      <button type="button" class="row-del" title="Remove">×</button>
    </div>`).join("");
  box.querySelectorAll(".row-del").forEach((b) =>
    b.addEventListener("click", () => { b.closest(".schema-row").remove(); ensureSchemaEmpty(); }));
}

function renderRuleRows(rules) {
  const box = $("#rule-rows");
  if (!rules.length) {
    box.innerHTML = `<p class="empty-rows">No quality rules yet.</p>`;
    return;
  }
  box.innerHTML = rules.map((r) => `
    <div class="rule-row">
      <input class="r-field" value="${esc(r.field)}" placeholder="(dataset)" />
      <select class="r-rule">${optionsHtml(OPTIONS.rule_types, r.rule || "not_null")}</select>
      <input class="r-desc" value="${esc(r.description)}" placeholder="description" />
      <button type="button" class="row-del" title="Remove">×</button>
    </div>`).join("");
  box.querySelectorAll(".row-del").forEach((b) =>
    b.addEventListener("click", () => { b.closest(".rule-row").remove(); ensureRuleEmpty(); }));
}

function ensureSchemaEmpty() {
  if (!$("#schema-rows").querySelector(".schema-row")) renderSchemaRows([]);
}
function ensureRuleEmpty() {
  if (!$("#rule-rows").querySelector(".rule-row")) renderRuleRows([]);
}

function appendSchemaRow(field) {
  const current = collectSchema();
  current.push(field || { name: "", type: "string", required: false, pii: false, description: "" });
  renderSchemaRows(current);
}
function appendRuleRow(rule) {
  const current = collectRules();
  current.push(rule || { field: "", rule: "not_null", description: "" });
  renderRuleRows(current);
}

function collectSchema() {
  return [...$("#schema-rows").querySelectorAll(".schema-row")].map((row) => ({
    name: row.querySelector(".f-name").value.trim(),
    type: row.querySelector(".f-type").value,
    required: row.querySelector(".f-req").checked,
    pii: row.querySelector(".f-pii").checked,
    description: row.querySelector(".f-desc").value.trim(),
  })).filter((f) => f.name);
}
function collectRules() {
  return [...$("#rule-rows").querySelectorAll(".rule-row")].map((row) => ({
    field: row.querySelector(".r-field").value.trim(),
    rule: row.querySelector(".r-rule").value,
    description: row.querySelector(".r-desc").value.trim(),
  }));
}

$("#add-field").addEventListener("click", () => appendSchemaRow());
$("#add-rule").addEventListener("click", () => appendRuleRow());
$("#contract-back").addEventListener("click", () => switchView("catalog"));

$("#contract-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#contract-msg");
  msg.textContent = ""; msg.className = "form-msg";
  const id = $("#contract-product-id").value;
  const payload = {
    version: $("#c-version").value.trim() || "1.0.0",
    status: $("#c-status").value,
    schema_fields: collectSchema(),
    quality_rules: collectRules(),
    slo_availability: $("#c-availability").value.trim(),
    slo_freshness: $("#c-freshness").value.trim(),
    slo_max_latency: $("#c-latency").value.trim(),
  };
  try {
    await api(`/data-products/${id}/contract`, jsonReq("PUT", payload));
    toast("Contract saved");
    switchView("catalog");
  } catch (err) {
    msg.textContent = err.message; msg.classList.add("err");
  }
});

$("#contract-delete").addEventListener("click", async () => {
  const id = $("#contract-product-id").value;
  if (!confirm("Delete this contract? This cannot be undone.")) return;
  try {
    await api(`/data-products/${id}/contract`, { method: "DELETE" });
    toast("Contract deleted");
    switchView("catalog");
  } catch (e) { toast("Delete failed: " + e.message); }
});

// AI assist for contracts
$("#ai-fill-c").addEventListener("click", async () => {
  const prompt = $("#ai-prompt-c").value.trim();
  const note = $("#ai-note-c");
  if (!prompt) { note.textContent = "Paste a sample or description first."; return; }
  const btn = $("#ai-fill-c");
  btn.disabled = true; btn.textContent = "Drafting…";
  note.textContent = "";
  try {
    const res = await api("/assist/contract", jsonReq("POST", { prompt }));
    const c = res.contract;
    renderSchemaRows(c.schema_fields || []);
    renderRuleRows(c.quality_rules || []);
    if (c.slo_availability) $("#c-availability").value = c.slo_availability;
    if (c.slo_freshness) $("#c-freshness").value = c.slo_freshness;
    if (c.slo_max_latency) $("#c-latency").value = c.slo_max_latency;
    [...$("#schema-rows").querySelectorAll(".schema-row"),
     ...$("#rule-rows").querySelectorAll(".rule-row")].forEach(flash);
    const n = (c.schema_fields || []).length;
    note.textContent = (res.source === "claude" ? "✓ Drafted by Claude. " : "✓ Drafted locally. ")
      + `${n} field${n === 1 ? "" : "s"} inferred. ` + (res.note || "Review before saving.");
    toast("Contract drafted — review the schema");
  } catch (e) {
    note.textContent = "Assistant error: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = "Draft the contract";
  }
});

bootstrap();
