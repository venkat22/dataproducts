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

// ---- Tabs -------------------------------------------------------------------
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchView(tab.dataset.view));
});
function switchView(view) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.view === view));
  $("#view-register").classList.toggle("hidden", view !== "register");
  $("#view-catalog").classList.toggle("hidden", view !== "catalog");
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
    fillSelect("#classification", opts.classifications);
    fillSelect("#update_frequency", opts.frequencies);
    fillSelect("#output_format", opts.formats);
  } catch (e) { /* selects stay empty; non-fatal */ }

  try {
    const health = await api("/health");
    const pill = $("#ai-status");
    if (health.ai_enabled) {
      pill.textContent = "Claude connected";
      pill.classList.add("on");
    } else {
      pill.textContent = "local mode";
      pill.classList.add("off");
    }
  } catch (e) {
    $("#ai-status").textContent = "offline";
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

bootstrap();
