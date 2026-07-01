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
  "classification", "update_frequency", "output_format", "sla", "tags",
];

// Demo data assets (Snowflake tables/views a producer can pick from)
const DEMO_DATA_ASSETS = [
  'inventory_health_dp', 'sales_order_backlog_dp', 'customer_360_dp',
  'finance_gl_summary_dp', 'marketing_campaign_dp', 'hr_workforce_dp',
  'iot_telemetry_dp', 'pricing_quote_dp', 'nrr_dashboard_dp',
  'supply_chain_forecast_dp', 'product_quality_dp', 'dealer_sales_dp',
];

let allProducts = [];
let OPTIONS = { classifications: [], frequencies: [], formats: [], contract_statuses: [], field_types: [], rule_types: [] };
let currentTab = 'published';
let currentDetailStep = 'overview';
let currentProduct = null;

// ── View routing ────────────────────────────────────────────────────
const VIEWS = ['home', 'browse', 'myproducts', 'register', 'contract', 'detail'];

function switchView(view) {
  VIEWS.forEach((v) => {
    const el = $(`#view-${v}`);
    if (el) el.classList.toggle('hidden', v !== view);
  });
  document.querySelectorAll('.nav-link').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.view === view ||
      (view === 'detail' && btn.dataset.view === 'browse'));
  });
  if (view === 'browse') loadCatalog();
  if (view === 'myproducts') loadMyCatalog();
  if (view === 'register') showRegisterLanding();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Wire nav links + hero buttons + brand logo
document.querySelectorAll('[data-view]').forEach((el) => {
  el.addEventListener('click', () => switchView(el.dataset.view));
});

// Hero search
$('#hero-search-go')?.addEventListener('click', doHeroSearch);
$('#hero-search-input')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') doHeroSearch(); });
document.querySelectorAll('.hero-kw-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const kw = chip.dataset.kw;
    const inp = $('#hero-search-input');
    if (inp) inp.value = kw;
    doHeroSearch();
  });
});

function doHeroSearch() {
  const q = $('#hero-search-input')?.value.trim() || '';
  switchView('browse');
  const searchInp = $('#search');
  if (searchInp && q) {
    searchInp.value = q;
    // Activate AI search mode for hero queries
    aiSearchMode = true;
    const btn = $('#ai-search-btn');
    if (btn) {
      btn.style.background = 'var(--orange-light)';
      btn.style.color = 'var(--orange)';
      btn.style.borderColor = 'var(--orange)';
    }
    setTimeout(() => runAiSearch(q), 300);
  }
}

// ── Toast ────────────────────────────────────────────────────────────
let toastTimer;
function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 2600);
}

// ── Escape helper ───────────────────────────────────────────────────
function flash(el) {
  if (!el) return;
  el.classList.remove('flash');
  void el.offsetWidth;
  el.classList.add('flash');
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ── Bootstrap ────────────────────────────────────────────────────────
async function bootstrap() {
  try {
    const opts = await api('/options');
    OPTIONS = opts;
    // Step 3 selects (new names)
    fillSelect('#classification-sel', opts.classifications);
    fillSelect('#update_frequency-sel', opts.frequencies);
    fillSelect('#output_format-sel', opts.formats);
    // Contract selects
    fillSelect('#c-status', opts.contract_statuses);
    fillSelect('#c2-status', opts.contract_statuses);
    buildDomainFilters();
    buildClassificationFilters();
  } catch (e) { /* non-fatal */ }

  try {
    const health = await api('/health');
    const label = health.ai_enabled ? 'Claude connected' : 'local mode';
    const cls = health.ai_enabled ? 'on' : 'off';
    ['#ai-status', '#ai-status-c'].forEach((sel) => {
      const pill = $(sel);
      if (pill) { pill.textContent = label; pill.className = `pill ${cls}`; }
    });
    // Update AI register badge
    const badge = $('#ai-reg-badge');
    if (badge) {
      if (health.ai_enabled) {
        badge.textContent = 'Claude AI Ready';
        badge.style.background = 'var(--orange)';
      } else {
        badge.textContent = 'Local Mode';
        badge.style.background = '#6b7280';
      }
    }
    const heading = $('#ai-reg-heading');
    if (heading) heading.textContent = health.ai_enabled
      ? 'AI-Powered Registration'
      : 'Smart Registration (Local Mode)';
    const sub = $('#ai-reg-subtext');
    if (sub) sub.textContent = health.ai_enabled
      ? 'Describe your data product in plain language and Claude AI will pre-fill the entire registration form for you.'
      : 'Describe your data product and the local keyword extractor will pre-fill the form. Add an ANTHROPIC_API_KEY to enable Claude AI.';
  } catch (e) {
    ['#ai-status', '#ai-status-c'].forEach((sel) => {
      const pill = $(sel);
      if (pill) { pill.textContent = 'offline'; pill.className = 'pill off'; }
    });
  }

  loadCatalog();
  switchView('home');
}

function fillSelect(sel, values) {
  const el = $(sel);
  if (!el) return;
  el.innerHTML = '';
  (values || []).forEach((v) => {
    const o = document.createElement('option');
    o.value = v; o.textContent = v;
    el.appendChild(o);
  });
}

// ── Filters ──────────────────────────────────────────────────────────
let activeFilters = { domains: new Set(), classifications: new Set(), scope: 'all' };

function buildDomainFilters() {
  const domains = [...new Set(allProducts.map(p => p.domain).filter(Boolean))].sort();
  // Build domain tab pills for browse view
  const tabsRow = $('#domain-tabs');
  if (tabsRow) {
    tabsRow.innerHTML = `<button class="domain-tab-btn active" data-domain="">All (${allProducts.length})</button>` +
      domains.map(d => {
        const count = allProducts.filter(p => p.domain === d).length;
        return `<button class="domain-tab-btn" data-domain="${esc(d)}">${esc(d)} (${count})</button>`;
      }).join('');
    tabsRow.querySelectorAll('.domain-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        tabsRow.querySelectorAll('.domain-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeFilters.domains.clear();
        if (btn.dataset.domain) activeFilters.domains.add(btn.dataset.domain);
        renderCatalog();
      });
    });
  }
  // Keep legacy checkbox DOM for filter sync (hidden, no longer shown)
  const box = $('#domain-filters');
  if (box) {
    box.innerHTML = domains.map(d => `<label class="filter-check" style="display:none;"><input type="checkbox" class="domain-check" value="${esc(d)}" /></label>`).join('');
  }
}

function buildClassificationFilters() {
  const box = $('#classification-filters');
  if (!box) return;
  box.innerHTML = (OPTIONS.classifications || []).map(c => `
    <label class="filter-check">
      <input type="checkbox" class="cls-check" value="${esc(c)}" />
      ${esc(c)}
    </label>
  `).join('');
  box.querySelectorAll('.cls-check').forEach((cb) => {
    cb.addEventListener('change', () => {
      if (cb.checked) activeFilters.classifications.add(cb.value);
      else activeFilters.classifications.delete(cb.value);
      renderActiveFilterChips();
      renderCatalog();
    });
  });
}

function renderActiveFilterChips() {
  const box = $('#active-filters');
  if (!box) return;
  const chips = [];
  activeFilters.domains.forEach(d => chips.push({ label: d, type: 'domain', value: d }));
  activeFilters.classifications.forEach(c => chips.push({ label: c, type: 'cls', value: c }));
  box.innerHTML = chips.map(chip => `
    <span class="active-filter-chip">
      ${esc(chip.label)}
      <button data-type="${chip.type}" data-value="${esc(chip.value)}">&times;</button>
    </span>
  `).join('');
  if (chips.length) {
    box.innerHTML += `<button class="clear-all-link" id="clear-all-filters">Clear all</button>`;
    $('#clear-all-filters').addEventListener('click', clearAllFilters);
  }
  box.querySelectorAll('.active-filter-chip button').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.dataset.type === 'domain') activeFilters.domains.delete(btn.dataset.value);
      else activeFilters.classifications.delete(btn.dataset.value);
      syncFilterCheckboxes();
      renderActiveFilterChips();
      renderCatalog();
    });
  });
}

function syncFilterCheckboxes() {
  document.querySelectorAll('.domain-check').forEach(cb => {
    cb.checked = activeFilters.domains.has(cb.value);
  });
  document.querySelectorAll('.cls-check').forEach(cb => {
    cb.checked = activeFilters.classifications.has(cb.value);
  });
}

function clearAllFilters() {
  activeFilters.domains.clear();
  activeFilters.classifications.clear();
  syncFilterCheckboxes();
  renderActiveFilterChips();
  renderCatalog();
}

$('#reset-filters')?.addEventListener('click', clearAllFilters);

document.querySelectorAll('[name="dp-scope"]').forEach((radio) => {
  radio.addEventListener('change', () => {
    activeFilters.scope = radio.value;
    renderCatalog();
  });
});

// ── AI Search ────────────────────────────────────────────────────────
let aiSearchMode = false;
let aiSearchFilters = null;

$('#ai-search-btn')?.addEventListener('click', () => {
  aiSearchMode = !aiSearchMode;
  const btn = $('#ai-search-btn');
  const input = $('#search');
  if (aiSearchMode) {
    btn.style.background = 'var(--orange-light)';
    btn.style.color = 'var(--orange)';
    btn.style.borderColor = 'var(--orange)';
    input.placeholder = 'Describe what you need… e.g. "daily finance data with PII"';
    input.focus();
  } else {
    btn.style.background = '';
    btn.style.color = '';
    btn.style.borderColor = '';
    input.placeholder = 'Search by name, description, tags...';
    aiSearchFilters = null;
    activeFilters.domains.clear();
    activeFilters.classifications.clear();
    syncFilterCheckboxes();
    renderActiveFilterChips();
    renderCatalog();
  }
});

let aiSearchTimer = null;
$('#search')?.addEventListener('input', () => {
  if (!aiSearchMode) { renderCatalog(); return; }
  clearTimeout(aiSearchTimer);
  const q = $('#search').value.trim();
  if (!q) { aiSearchFilters = null; renderCatalog(); return; }
  aiSearchTimer = setTimeout(() => runAiSearch(q), 700);
});

async function runAiSearch(query) {
  const btn = $('#ai-search-btn');
  const origText = btn.textContent;
  btn.textContent = '⏳ Searching…';
  try {
    const res = await api('/assist/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }) });
    const f = res.filters;
    activeFilters.domains.clear();
    (f.domains || []).forEach(d => activeFilters.domains.add(d));
    activeFilters.classifications.clear();
    (f.classifications || []).forEach(c => activeFilters.classifications.add(c));
    syncFilterCheckboxes();
    aiSearchFilters = { contains_pii: f.contains_pii, tags: f.tags || [], rerank_ids: f.rerank_ids || [], query };
    renderActiveFilterChips();
    renderCatalog();
  } catch (e) {
    // fall back to normal search
    aiSearchFilters = null;
    renderCatalog();
  } finally {
    btn.textContent = origText;
  }
}

// ── Catalog / Browse ─────────────────────────────────────────────────
async function loadCatalog() {
  try {
    allProducts = await api('/data-products');
    buildDomainFilters();
    buildClassificationFilters();
    renderCatalog();
  } catch (e) {
    $('#catalog-list').innerHTML = `<p class="empty-state">${esc(e.message)}</p>`;
  }
}

// search input is handled in the AI Search section below (handles both modes)
$('#sort-select')?.addEventListener('change', () => renderCatalog());

function renderCatalog() {
  const q = ($('#search')?.value || '').trim().toLowerCase();
  const sort = $('#sort-select')?.value || 'az';
  const list = $('#catalog-list');
  if (!list) return;

  let items = allProducts.filter((p) => {
    if (!aiSearchMode && q && !`${p.name} ${p.description} ${p.domain} ${p.tags} ${p.owner_name}`.toLowerCase().includes(q)) return false;
    if (activeFilters.domains.size && !activeFilters.domains.has(p.domain)) return false;
    if (activeFilters.classifications.size && !activeFilters.classifications.has(p.classification)) return false;
    if (aiSearchFilters?.contains_pii === true && !p.contains_pii) return false;
    if (aiSearchFilters?.contains_pii === false && p.contains_pii) return false;
    return true;
  });

  // AI re-ranking: order by rerank_ids if present, else normal sort
  if (aiSearchFilters?.rerank_ids?.length) {
    const order = aiSearchFilters.rerank_ids;
    items = [...items].sort((a, b) => {
      const ia = order.indexOf(a.id), ib = order.indexOf(b.id);
      if (ia === -1 && ib === -1) return 0;
      if (ia === -1) return 1;
      if (ib === -1) return -1;
      return ia - ib;
    });
  } else {
    items = [...items].sort((a, b) => {
      if (sort === 'az') return a.name.localeCompare(b.name);
      if (sort === 'za') return b.name.localeCompare(a.name);
      return 0;
    });
  }

  const totalCount = $('#catalog-count');
  if (totalCount) totalCount.textContent = allProducts.length;

  if (!items.length) {
    list.innerHTML = `<div class="empty-state">
      <strong>${allProducts.length ? 'No results match your filters.' : 'No data products registered yet.'}</strong>
      <p>${allProducts.length ? 'Try adjusting filters or search.' : 'Go to Register to add one.'}</p>
    </div>`;
    return;
  }

  list.innerHTML = items.map((p) => `
    <div class="dp-card">
      <div class="dp-card-top">
        <div class="dp-card-meta">
          <span>&#128065; ${Math.floor(Math.random() * 500) + 50}</span>
          <span>&#128260; ${p.updated_at ? p.updated_at.split('T')[0] : '—'}</span>
        </div>
        <button class="bookmark-btn" title="Bookmark">&#9711;</button>
      </div>
      <div class="dp-card-title">${esc(p.name)}</div>
      <div class="dp-card-tags">
        ${p.domain ? `<span class="tag tag-orange">${esc(p.domain)}</span>` : ''}
        ${p.classification ? `<span class="tag tag-blue">${esc(p.classification)}</span>` : ''}
        ${p.contains_pii ? `<span class="tag tag-danger">PII</span>` : ''}
        ${p.has_contract ? `<span class="tag tag-green">&#10003; Contract</span>` : ''}
      </div>
      <p class="dp-card-desc">${esc(p.description) || '<em>No description</em>'}</p>
      <div class="dp-card-owner">
        ${p.owner_name ? `<div class="dp-card-owner-row">&#9679; ${esc(p.owner_name)}</div>` : ''}
        ${p.owner_email ? `<div class="dp-card-owner-row">&#9993; <a href="mailto:${esc(p.owner_email)}">${esc(p.owner_email)}</a></div>` : ''}
      </div>
      <div class="dp-card-foot">
        <div class="dp-card-plain-tags">${tagChips(p.tags)}</div>
        <button class="btn view-details" data-view-detail="${p.id}">View Details</button>
      </div>
    </div>
  `).join('');

  list.querySelectorAll('[data-view-detail]').forEach((btn) => {
    btn.addEventListener('click', () => openDetail(allProducts.find(p => p.id == btn.dataset.viewDetail)));
  });
}

function tagChips(tags) {
  if (!tags) return '';
  return tags.split(',').map(t => t.trim()).filter(Boolean)
    .map(t => `<span class="plain-tag">${esc(t)}</span>`).join('');
}

// ── My Data Products ─────────────────────────────────────────────────
async function loadMyCatalog() {
  try {
    const products = await api('/data-products');
    const myCount = $('#my-count');
    if (myCount) { myCount.textContent = products.length; myCount.classList.toggle('hidden', !products.length); }
    renderMyTabs(products);
  } catch (e) { /* non-fatal */ }
}

function renderMyTabs(products) {
  const published = products;
  const review = [];
  const subscribed = products;

  $('#published-count').textContent = published.length;
  $('#review-count').textContent = review.length;
  $('#subscribed-count').textContent = subscribed.length;

  renderMyProducts(products, currentTab);
}

document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentTab = btn.dataset.tab;
    loadMyCatalog();
  });
});

$('#my-search')?.addEventListener('input', loadMyCatalog);

function renderMyProducts(products, tab) {
  const q = ($('#my-search')?.value || '').trim().toLowerCase();
  const list = $('#my-catalog-list');
  if (!list) return;

  let items = products.filter(p =>
    !q || `${p.name} ${p.description} ${p.tags}`.toLowerCase().includes(q));

  if (!items.length) {
    list.innerHTML = `<div class="empty-state"><strong>No data products yet.</strong>
      <p>Click "Register New Data Product" to add one.</p></div>`;
    return;
  }

  list.innerHTML = items.map((p) => `
    <div class="dp-card">
      <div class="dp-card-top">
        <div class="dp-card-meta">
          <span>&#128065; ${Math.floor(Math.random() * 5000) + 100}</span>
          <span>&#128260; ${p.updated_at ? p.updated_at.split('T')[0] : '—'}</span>
        </div>
        <button class="bookmark-btn">&#9711;</button>
      </div>
      <div class="dp-card-title">${esc(p.name)}</div>
      <div class="dp-card-tags">
        ${p.domain ? `<span class="tag tag-orange">${esc(p.domain)}</span>` : ''}
        ${p.classification ? `<span class="tag tag-blue">${esc(p.classification)}</span>` : ''}
      </div>
      <p class="dp-card-desc">${esc(p.description) || '<em>No description</em>'}</p>
      <div class="dp-card-owner">
        ${p.owner_name ? `<div class="dp-card-owner-row">&#9679; ${esc(p.owner_name)}</div>` : ''}
        ${p.owner_email ? `<div class="dp-card-owner-row">&#9993; <a href="mailto:${esc(p.owner_email)}">${esc(p.owner_email)}</a></div>` : ''}
      </div>
      <div class="dp-card-plain-tags">${tagChips(p.tags)}</div>
      <div class="dp-card-foot" style="margin-top:8px;">
        <div style="display:flex;gap:8px;">
          <button class="btn ghost sm" data-edit="${p.id}">Edit</button>
          <button class="btn sm" style="background:none;border:1px solid #fca5a5;color:#dc2626;" data-del="${p.id}">Delete</button>
          <button class="btn ghost sm" data-contract="${p.id}">${p.has_contract ? 'Contract' : '+ Contract'}</button>
        </div>
        <button class="btn view-details" data-view-detail="${p.id}">View Details</button>
      </div>
    </div>
  `).join('');

  list.querySelectorAll('[data-edit]').forEach(btn =>
    btn.addEventListener('click', () => editProduct(products.find(p => p.id == btn.dataset.edit))));
  list.querySelectorAll('[data-del]').forEach(btn =>
    btn.addEventListener('click', () => { const p = products.find(x => x.id == btn.dataset.del); deleteProduct(p.id, p.name); }));
  list.querySelectorAll('[data-contract]').forEach(btn =>
    btn.addEventListener('click', () => openContract(products.find(p => p.id == btn.dataset.contract))));
  list.querySelectorAll('[data-view-detail]').forEach(btn =>
    btn.addEventListener('click', () => openDetail(products.find(p => p.id == btn.dataset.viewDetail))));
}

// ── Product detail ───────────────────────────────────────────────────
function openDetail(product) {
  if (!product) return;
  currentProduct = product;
  $('#detail-title').textContent = product.name;
  $('#detail-desc').textContent = product.description || '';
  $('#detail-tags').innerHTML = [
    product.domain ? `<span class="tag tag-orange">${esc(product.domain)}</span>` : '',
    product.classification ? `<span class="tag tag-blue">${esc(product.classification)}</span>` : '',
    product.contains_pii ? `<span class="tag tag-danger">PII</span>` : '',
    product.has_contract ? `<span class="tag tag-green">&#10003; Contract</span>` : '',
    ...tagChips(product.tags).split('</span>').filter(Boolean).map(t => t + '</span>'),
  ].join('');

  $('#detail-kv').innerHTML = [
    product.update_frequency ? `<div class="detail-kv-item">&#128260; <b>Updated on:</b> ${esc(product.updated_at ? product.updated_at.split('T')[0] : '—')}</div>` : '',
    product.classification ? `<div class="detail-kv-item">&#128204; <b>Type</b> ${esc(product.classification)}</div>` : '',
    product.domain ? `<div class="detail-kv-item">&#127970; <b>Function:</b> ${esc(product.domain)}</div>` : '',
  ].join('');

  $('#overview-fields').innerHTML = [
    product.domain ? `<div><div class="kv-label">Business Function</div><div class="kv-value">${esc(product.domain)}</div></div>` : '',
    product.owner_name ? `<div><div class="kv-label">Owner</div><div class="kv-value">${esc(product.owner_name)}</div></div>` : '',
    product.owner_email ? `<div><div class="kv-label">Contact</div><div class="kv-value">${esc(product.owner_email)}</div></div>` : '',
    product.output_format ? `<div><div class="kv-label">Output Format</div><div class="kv-value">${esc(product.output_format)}</div></div>` : '',
    product.update_frequency ? `<div><div class="kv-label">Update Frequency</div><div class="kv-value">${esc(product.update_frequency)}</div></div>` : '',
    product.sla ? `<div><div class="kv-label">SLA</div><div class="kv-value">${esc(product.sla)}</div></div>` : '',
  ].join('');

  $('#input-ports-content').innerHTML = product.source_systems
    ? product.source_systems.split(',').map(s => `<span class="tag tag-gray" style="margin:3px;">${esc(s.trim())}</span>`).join('')
    : '<span style="color:var(--muted);font-size:13px;">No input ports defined.</span>';

  $('#source-data-content').innerHTML = '<span style="color:var(--muted);font-size:13px;">Source data information not available.</span>';

  $('#output-ports-content').innerHTML = product.has_contract
    ? `<button class="btn ghost sm" id="view-contract-from-detail">View Contract</button>`
    : '<span style="color:var(--muted);font-size:13px;">No output ports / contract defined yet.</span>';

  $('#data-quality-content').innerHTML = product.has_contract
    ? `<button class="btn ghost sm" id="view-dq-contract">View contract rules</button>`
    : '<span style="color:var(--muted);font-size:13px;">No data quality rules yet.</span>';

  // Reset Vega chat
  const vegaMessages = $('#vega-messages');
  if (vegaMessages) vegaMessages.innerHTML = '';
  $('#vega-chat-panel')?.classList.add('hidden');
  $('#vega-note') && ($('#vega-note').textContent = '');

  switchDetailTab('overview');
  switchView('detail');

  // Load similar products after render
  loadSimilarProducts(product);

  // Re-wire detail contract buttons
  setTimeout(() => {
    $('#view-contract-from-detail')?.addEventListener('click', () => openContract(product));
    $('#view-dq-contract')?.addEventListener('click', () => openContract(product));
  }, 50);
}

document.querySelectorAll('[data-detail-tab]').forEach((btn) => {
  btn.addEventListener('click', () => switchDetailTab(btn.dataset.detailTab));
});

function switchDetailTab(tab) {
  document.querySelectorAll('[data-detail-tab]').forEach(b => b.classList.toggle('active', b.dataset.detailTab === tab));
  ['overview', 'input-ports', 'source-data', 'data-quality', 'output-ports'].forEach(t => {
    const el = $(`#pane-${t}`);
    if (el) el.classList.toggle('hidden', t !== tab);
  });
}

$('#detail-back-browse')?.addEventListener('click', () => switchView('browse'));

// ── Register – stepper ───────────────────────────────────────────────
let currentStep = 1;

function showRegisterLanding() {
  $('#register-landing').classList.remove('hidden');
  $('#register-form-wrapper').classList.add('hidden');
  $('#register-page-title').textContent = 'Register New Data Product';
  resetRegisterForm();
}

$('#start-manual')?.addEventListener('click', () => {
  $('#register-landing').classList.add('hidden');
  $('#register-form-wrapper').classList.remove('hidden');
  clarifyAllowed = true;
  hideClarifyPanel();
  currentStep = 1;
  renderStepper(1);
  showStep(1);
  setupClarifyTriggers();
  initAssetPicker();
});

$('#ai-reg-fill')?.addEventListener('click', async () => {
  const prompt = $('#ai-reg-prompt')?.value?.trim();
  const note = $('#ai-reg-note');
  if (!prompt) { if (note) note.textContent = 'Please describe your data product first.'; return; }

  const btn = $('#ai-reg-fill');
  btn.disabled = true;
  btn.textContent = '⏳ Thinking…';
  if (note) note.textContent = '';

  try {
    const res = await api('/assist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    });

    // Show the stepper form
    $('#register-landing').classList.add('hidden');
    $('#register-form-wrapper').classList.remove('hidden');
    clarifyAllowed = true;
    hideClarifyPanel();
    showStep(1);
    setupClarifyTriggers();
    initAssetPicker();

    // Apply all returned fields to the form
    const fields = res.fields;
    FIELD_KEYS.forEach(k => {
      const el = $(`#${k}`);
      if (el && fields[k] != null) el.value = fields[k];
    });
    if ($('#contains_pii')) $('#contains_pii').checked = !!fields.contains_pii;

    // Handle source_systems tag input
    if (fields.source_systems) {
      $('#source_systems').value = fields.source_systems;
      renderTagItems('source-tags-wrap', 'source-tag-input', 'source-tag-add', 'source_systems',
        fields.source_systems.split(',').map(t => t.trim()).filter(Boolean));
    }
    // Handle tags input
    if (fields.tags) {
      $('#tags').value = fields.tags;
      renderTagItems('tags-wrap', 'tags-input', 'tags-add', 'tags',
        fields.tags.split(',').map(t => t.trim()).filter(Boolean));
    }

    // Flash all filled fields
    FIELD_KEYS.forEach(k => { const el = $(`#${k}`); if (el) flash(el); });

    const src = res.source === 'claude' ? '✓ Filled by Claude AI.' : '✓ Filled by local extraction.';
    toast(`Form pre-filled — review and continue`);

    // Show a note on step 1
    const msg = $('#form-msg');
    if (msg) {
      msg.textContent = `${src} ${res.note || 'Review each step and adjust before submitting.'}`;
      msg.className = 'form-msg ok';
    }
  } catch (e) {
    if (note) note.textContent = 'AI error: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ Fill form with AI';
  }
});

function renderStepper(active) {
  document.querySelectorAll('.step').forEach((el) => {
    const n = +el.dataset.step;
    el.classList.toggle('active', n === active);
    el.classList.toggle('done', n < active);
    const circle = el.querySelector('.step-circle');
    if (n < active) circle.innerHTML = '&#10003;';
    else circle.textContent = n;
  });
}

function showStep(n) {
  for (let i = 1; i <= 4; i++) $(`#step-${i}`)?.classList.toggle('hidden', i !== n);
  renderStepper(n);
  currentStep = n;
}

// Step nav
$('#step1-cancel')?.addEventListener('click', showRegisterLanding);
$('#step1-next')?.addEventListener('click', async () => {
  const name = $('#name').value.trim();
  if (!name) { const msg = $('#form-msg'); msg.textContent = 'Product Name is required.'; msg.className = 'form-msg err'; return; }
  $('#form-msg').textContent = '';

  // Always block if clarify panel is currently visible — user must answer or skip first
  if (!$('#clarify-panel')?.classList.contains('hidden')) return;

  // Run quality check (fires if the blur debounce hasn't triggered yet)
  if (clarifyAllowed) {
    await runClarifyCheck();
    if (!$('#clarify-panel')?.classList.contains('hidden')) return;
  }

  showStep(2);
});

$('#step2-cancel')?.addEventListener('click', showRegisterLanding);
$('#step2-back')?.addEventListener('click', () => showStep(1));
$('#step2-next')?.addEventListener('click', () => showStep(3));

$('#step3-cancel')?.addEventListener('click', showRegisterLanding);
$('#step3-back')?.addEventListener('click', () => showStep(2));
$('#step3-next')?.addEventListener('click', () => {
  // Sync selects to hidden fields before advancing
  const cls = $('#classification-sel'); if (cls) $('#classification').value = cls.value;
  const freq = $('#update_frequency-sel'); if (freq) $('#update_frequency').value = freq.value;
  const fmt = $('#output_format-sel'); if (fmt) $('#output_format').value = fmt.value;
  const slaInp = $('#sla-inp'); if (slaInp) $('#sla').value = slaInp.value;
  const piiCheck = $('#contains_pii_check'); if (piiCheck) $('#contains_pii').value = piiCheck.checked ? 'true' : 'false';
  showStep(4);
});

$('#step4-cancel')?.addEventListener('click', showRegisterLanding);
$('#step4-back')?.addEventListener('click', () => showStep(3));
$('#step4-submit')?.addEventListener('click', submitProduct);

// Tag input widgets
function initTagInput(wrapId, inputId, addBtnId, hiddenId) {
  const wrap = $(`#${wrapId}`);
  const inp = $(`#${inputId}`);
  const btn = $(`#${addBtnId}`);
  const hidden = $(`#${hiddenId}`);
  if (!wrap || !inp) return;

  const addTag = () => {
    const val = inp.value.trim();
    if (!val) return;
    const tags = getTagValues(wrapId, hiddenId);
    if (tags.includes(val)) { inp.value = ''; return; }
    tags.push(val);
    inp.value = '';
    renderTagItems(wrapId, inputId, addBtnId, hiddenId, tags);
  };

  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } });
  btn?.addEventListener('click', addTag);
  wrap.addEventListener('click', () => inp.focus());
}

function getTagValues(wrapId, hiddenId) {
  const h = $(`#${hiddenId}`);
  return h?.value ? h.value.split(',').map(t => t.trim()).filter(Boolean) : [];
}

function renderTagItems(wrapId, inputId, addBtnId, hiddenId, tags) {
  const wrap = $(`#${wrapId}`);
  const inp = $(`#${inputId}`);
  const btn = $(`#${addBtnId}`);
  const hidden = $(`#${hiddenId}`);

  // Clear existing tag items (keep input and add btn)
  wrap.querySelectorAll('.tag-input-item').forEach(t => t.remove());

  // Prepend tags before the input
  tags.forEach(tag => {
    const span = document.createElement('span');
    span.className = 'tag-input-item';
    span.innerHTML = `${esc(tag)} <button type="button">&times;</button>`;
    span.querySelector('button').addEventListener('click', () => {
      const updated = tags.filter(t => t !== tag);
      renderTagItems(wrapId, inputId, addBtnId, hiddenId, updated);
    });
    wrap.insertBefore(span, inp);
  });

  if (hidden) hidden.value = tags.join(',');
}

initTagInput('source-tags-wrap', 'source-tag-input', 'source-tag-add', 'source_systems');
initTagInput('tags-wrap', 'tags-input', 'tags-add', 'tags');

// ── Submit product ───────────────────────────────────────────────────
async function submitProduct() {
  const msg = $('#step5-msg') || $('#form-msg');
  if (msg) { msg.textContent = ''; msg.className = 'form-msg'; }

  const payload = collectForm();
  if (!payload.name) {
    if (msg) { msg.textContent = 'Product Name is required.'; msg.className = 'form-msg err'; }
    return;
  }

  const id = $('#product_id').value;
  const btn = $('#step4-submit') || $('#step5-submit');
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

  try {
    if (id) {
      await api(`/data-products/${id}`, jsonReq('PUT', payload));
      toast('Data product updated');
    } else {
      const created = await api('/data-products', jsonReq('POST', payload));
      toast('Data product registered');

      // Save contract from step 4 if any schema rows were filled
      const contractPayload = collectContract();
      if (contractPayload.schema_fields.length || contractPayload.quality_rules.length) {
        await api(`/data-products/${created.id}/contract`, jsonReq('PUT', contractPayload)).catch(() => {});
      }
    }
    resetRegisterForm();
    switchView('myproducts');
  } catch (err) {
    if (msg) { msg.textContent = err.message; msg.className = 'form-msg err'; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Submit'; }
  }
}

const jsonReq = (method, body) => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

function collectForm() {
  const data = {};
  FIELD_KEYS.forEach(k => { data[k] = $(`#${k}`)?.value ?? ''; });
  data.source_systems = $('#source_systems')?.value ?? '';
  // contains_pii from hidden field (set by step3 sync)
  const piiVal = $('#contains_pii')?.value;
  data.contains_pii = piiVal === 'true' || $('#contains_pii_check')?.checked === true;
  // subdomain → store in domain if domain is blank
  const sub = $('#subdomain')?.value?.trim();
  if (sub && !data.domain) data.domain = sub;
  return data;
}

function resetRegisterForm() {
  FIELD_KEYS.forEach(k => { const el = $(`#${k}`); if (el) el.value = ''; });
  const pii = $('#contains_pii'); if (pii) pii.checked = false;
  const pid = $('#product_id'); if (pid) pid.value = '';
  const src = $('#source_systems'); if (src) src.value = '';
  const tags = $('#tags'); if (tags) tags.value = '';
  $('#source-tags-wrap')?.querySelectorAll('.tag-input-item').forEach(t => t.remove());
  $('#tags-wrap')?.querySelectorAll('.tag-input-item').forEach(t => t.remove());
  $('#form-msg').textContent = '';
  const subdomain = $('#subdomain'); if (subdomain) subdomain.value = '';
  const slaInp = $('#sla-inp'); if (slaInp) slaInp.value = '';
  const piiCheck = $('#contains_pii_check'); if (piiCheck) piiCheck.checked = false;
  const clsSel = $('#classification-sel'); if (clsSel) clsSel.value = clsSel.options[0]?.value || '';
  const freqSel = $('#update_frequency-sel'); if (freqSel) freqSel.value = freqSel.options[0]?.value || '';
  const fmtSel = $('#output_format-sel'); if (fmtSel) fmtSel.value = fmtSel.options[0]?.value || '';
  // Reset asset picker
  selectedAssets = [];
  renderAssetChips();
  if ($('#source_systems')) $('#source_systems').value = '';
  $('#asset-duplicate-warning')?.classList.add('hidden');
  hideClarifyPanel();
  clarifyAllowed = true;
  showStep(1);
}

function editProduct(p) {
  if (!p) return;
  FIELD_KEYS.forEach(k => { const el = $(`#${k}`); if (el && p[k] != null) el.value = p[k]; });
  if ($('#contains_pii')) $('#contains_pii').checked = !!p.contains_pii;
  if ($('#product_id')) $('#product_id').value = p.id;
  if ($('#source_systems')) $('#source_systems').value = p.source_systems || '';
  if ($('#tags')) $('#tags').value = p.tags || '';

  // Render tag items
  renderTagItems('source-tags-wrap', 'source-tag-input', 'source-tag-add', 'source_systems',
    (p.source_systems || '').split(',').map(t => t.trim()).filter(Boolean));
  renderTagItems('tags-wrap', 'tags-input', 'tags-add', 'tags',
    (p.tags || '').split(',').map(t => t.trim()).filter(Boolean));

  $('#register-landing').classList.add('hidden');
  $('#register-form-wrapper').classList.remove('hidden');
  $('#register-page-title').textContent = `Edit: ${p.name}`;
  showStep(1);
  switchView('register');
}

async function deleteProduct(id, name) {
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  try {
    await api(`/data-products/${id}`, { method: 'DELETE' });
    toast('Deleted');
    loadMyCatalog();
  } catch (e) { toast('Delete failed: ' + e.message); }
}

// ── Contract (standalone view) ────────────────────────────────────────
let contractProductId = null;

async function openContract(product) {
  if (!product) return;
  contractProductId = product.id;
  $('#contract-product-id').value = product.id;
  $('#contract-product').textContent = `Contract for: ${product.name}`;
  $('#contract-msg').textContent = '';
  $('#contract-delete').classList.add('hidden');

  let contract = blankContract();
  let exists = false;
  if (product.has_contract) {
    try { contract = await api(`/data-products/${product.id}/contract`); exists = true; } catch (e) { /* blank */ }
  }
  fillContract(contract, 'c2-version', 'c2-status', 'c2-availability', 'c2-freshness', 'c2-latency', 'schema-rows-2', 'rule-rows-2');
  if (exists) $('#contract-delete').classList.remove('hidden');
  switchView('contract');
}

$('#contract-back')?.addEventListener('click', () => switchView(currentProduct ? 'detail' : 'browse'));
$('#contract-cancel')?.addEventListener('click', () => switchView('browse'));

$('#contract-save')?.addEventListener('click', async () => {
  const msg = $('#contract-msg');
  msg.textContent = ''; msg.className = 'form-msg';
  const payload = {
    version: $('#c2-version').value.trim() || '1.0.0',
    status: $('#c2-status').value,
    schema_fields: collectSchema('schema-rows-2'),
    quality_rules: collectRules('rule-rows-2'),
    slo_availability: $('#c2-availability').value.trim(),
    slo_freshness: $('#c2-freshness').value.trim(),
    slo_max_latency: $('#c2-latency').value.trim(),
  };
  try {
    await api(`/data-products/${contractProductId}/contract`, jsonReq('PUT', payload));
    toast('Contract saved');
    switchView('browse');
  } catch (err) { msg.textContent = err.message; msg.className = 'form-msg err'; }
});

$('#contract-delete')?.addEventListener('click', async () => {
  if (!confirm('Delete this contract? This cannot be undone.')) return;
  try {
    await api(`/data-products/${contractProductId}/contract`, { method: 'DELETE' });
    toast('Contract deleted');
    switchView('browse');
  } catch (e) { toast('Delete failed: ' + e.message); }
});

// Step 4 contract helpers
$('#add-field')?.addEventListener('click', () => appendSchemaRow(null, 'schema-rows', 'add-field'));
$('#add-rule')?.addEventListener('click', () => appendRuleRow(null, 'rule-rows', 'add-rule'));
$('#add-field-2')?.addEventListener('click', () => appendSchemaRow(null, 'schema-rows-2', 'add-field-2'));
$('#add-rule-2')?.addEventListener('click', () => appendRuleRow(null, 'rule-rows-2', 'add-rule-2'));

function blankContract() {
  return { version: '1.0.0', status: 'draft', schema_fields: [], quality_rules: [], slo_availability: '', slo_freshness: '', slo_max_latency: '' };
}

function fillContract(c, verId, statId, availId, freshId, latId, schemaId, ruleId) {
  const get = (id) => $(id.startsWith('#') ? id : `#${id}`);
  if (get(verId)) get(verId).value = c.version || '1.0.0';
  if (get(statId)) get(statId).value = c.status || 'draft';
  if (get(availId)) get(availId).value = c.slo_availability || '';
  if (get(freshId)) get(freshId).value = c.slo_freshness || '';
  if (get(latId)) get(latId).value = c.slo_max_latency || '';
  renderSchemaRows(c.schema_fields || [], schemaId);
  renderRuleRows(c.quality_rules || [], ruleId);
}

function collectContract() {
  return {
    version: $('#c-version')?.value?.trim() || '1.0.0',
    status: $('#c-status')?.value || 'draft',
    schema_fields: collectSchema('schema-rows'),
    quality_rules: collectRules('rule-rows'),
    slo_availability: $('#c-availability')?.value?.trim() || '',
    slo_freshness: $('#c-freshness')?.value?.trim() || '',
    slo_max_latency: $('#c-latency')?.value?.trim() || '',
  };
}

function optionsHtml(values, selected) {
  return (values || []).map(v =>
    `<option value="${esc(v)}" ${v === selected ? 'selected' : ''}>${esc(v)}</option>`).join('');
}

function renderSchemaRows(fields, boxId) {
  const box = $(`#${boxId}`);
  if (!box) return;
  if (!fields.length) { box.innerHTML = `<p class="empty-rows">No fields yet.</p>`; return; }
  box.innerHTML = fields.map(f => `
    <div class="schema-row">
      <input class="f-name" value="${esc(f.name)}" placeholder="field_name" />
      <select class="f-type">${optionsHtml(OPTIONS.field_types, f.type || 'string')}</select>
      <span class="cell-check"><input type="checkbox" class="f-req" ${f.required ? 'checked' : ''} /></span>
      <span class="cell-check"><input type="checkbox" class="f-pii" ${f.pii ? 'checked' : ''} /></span>
      <input class="f-desc" value="${esc(f.description)}" placeholder="description" />
      <button type="button" class="row-del" title="Remove">&times;</button>
    </div>`).join('');
  box.querySelectorAll('.row-del').forEach(b =>
    b.addEventListener('click', () => { b.closest('.schema-row').remove(); if (!box.querySelector('.schema-row')) renderSchemaRows([], boxId); }));
}

function renderRuleRows(rules, boxId) {
  const box = $(`#${boxId}`);
  if (!box) return;
  if (!rules.length) { box.innerHTML = `<p class="empty-rows">No rules yet.</p>`; return; }
  box.innerHTML = rules.map(r => `
    <div class="rule-row">
      <input class="r-field" value="${esc(r.field)}" placeholder="(dataset)" />
      <select class="r-rule">${optionsHtml(OPTIONS.rule_types, r.rule || 'not_null')}</select>
      <input class="r-desc" value="${esc(r.description)}" placeholder="description" />
      <button type="button" class="row-del" title="Remove">&times;</button>
    </div>`).join('');
  box.querySelectorAll('.row-del').forEach(b =>
    b.addEventListener('click', () => { b.closest('.rule-row').remove(); if (!box.querySelector('.rule-row')) renderRuleRows([], boxId); }));
}

function appendSchemaRow(field, boxId, addBtnId) {
  const current = collectSchema(boxId);
  current.push(field || { name: '', type: 'string', required: false, pii: false, description: '' });
  renderSchemaRows(current, boxId);
}

function appendRuleRow(rule, boxId, addBtnId) {
  const current = collectRules(boxId);
  current.push(rule || { field: '', rule: 'not_null', description: '' });
  renderRuleRows(current, boxId);
}

function collectSchema(boxId) {
  return [...($(`#${boxId}`)?.querySelectorAll('.schema-row') || [])].map(row => ({
    name: row.querySelector('.f-name').value.trim(),
    type: row.querySelector('.f-type').value,
    required: row.querySelector('.f-req').checked,
    pii: row.querySelector('.f-pii').checked,
    description: row.querySelector('.f-desc').value.trim(),
  })).filter(f => f.name);
}

function collectRules(boxId) {
  return [...($(`#${boxId}`)?.querySelectorAll('.rule-row') || [])].map(row => ({
    field: row.querySelector('.r-field').value.trim(),
    rule: row.querySelector('.r-rule').value,
    description: row.querySelector('.r-desc').value.trim(),
  }));
}

// ── Asset picker (Step 2) ────────────────────────────────────────────
let selectedAssets = [];

function initAssetPicker() {
  const wrap = $('#asset-picker-wrap');
  const input = $('#asset-search-input');
  const dropdown = $('#asset-dropdown');
  if (!wrap || !input || !dropdown) return;

  input.addEventListener('focus', () => renderAssetDropdown(input.value));
  input.addEventListener('input', () => renderAssetDropdown(input.value));
  document.addEventListener('click', (e) => {
    if (!wrap.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.add('hidden');
    }
  });
  wrap.addEventListener('click', () => input.focus());
}

function renderAssetDropdown(query) {
  const dropdown = $('#asset-dropdown');
  const list = $('#asset-dropdown-list');
  if (!dropdown || !list) return;

  const q = query.toLowerCase().trim();
  const filtered = DEMO_DATA_ASSETS.filter(a =>
    !q || a.toLowerCase().includes(q)
  );

  if (!filtered.length) {
    list.innerHTML = `<div class="asset-dropdown-empty">No assets found</div>`;
  } else {
    list.innerHTML = filtered.map(a => {
      const checked = selectedAssets.includes(a);
      return `<div class="asset-dropdown-item" data-asset="${esc(a)}">
        <input type="checkbox" ${checked ? 'checked' : ''} />
        <span>${esc(a)}</span>
      </div>`;
    }).join('');
    list.querySelectorAll('.asset-dropdown-item').forEach(item => {
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        const asset = item.dataset.asset;
        const cb = item.querySelector('input');
        if (selectedAssets.includes(asset)) {
          selectedAssets = selectedAssets.filter(a => a !== asset);
          if (cb) cb.checked = false;
        } else {
          selectedAssets.push(asset);
          if (cb) cb.checked = true;
        }
        renderAssetChips();
        syncAssetField();
        checkAssetDuplicate(asset);
      });
    });
  }
  dropdown.classList.remove('hidden');
}

function renderAssetChips() {
  const chipsEl = $('#asset-selected-chips');
  if (!chipsEl) return;
  chipsEl.innerHTML = selectedAssets.map(a => `
    <span class="asset-chip">
      ${esc(a)}
      <button type="button" data-remove="${esc(a)}">&times;</button>
    </span>
  `).join('');
  chipsEl.querySelectorAll('[data-remove]').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedAssets = selectedAssets.filter(a => a !== btn.dataset.remove);
      renderAssetChips();
      syncAssetField();
    });
  });
}

function syncAssetField() {
  const hidden = $('#source_systems');
  if (hidden) hidden.value = selectedAssets.join(', ');
}

async function checkAssetDuplicate(assetName) {
  const warn = $('#asset-duplicate-warning');
  const cards = $('#asset-duplicate-cards');
  if (!warn || !cards) return;
  // Check if any existing product uses this asset
  const matches = allProducts.filter(p =>
    p.source_systems && p.source_systems.toLowerCase().includes(assetName.toLowerCase())
  );
  if (matches.length) {
    cards.innerHTML = matches.map(p => `
      <div class="dp-card" style="margin-top:8px;">
        <div class="dp-card-title">${esc(p.name)}</div>
        <div class="dp-card-desc">${esc(p.description?.slice(0,100) || '')}…</div>
        <div style="margin-top:8px;">
          <button class="btn ghost sm" data-view-detail="${p.id}">View Details</button>
        </div>
      </div>
    `).join('');
    cards.querySelectorAll('[data-view-detail]').forEach(btn =>
      btn.addEventListener('click', () => openDetail(allProducts.find(p => p.id == btn.dataset.viewDetail)))
    );
    warn.classList.remove('hidden');
  } else {
    warn.classList.add('hidden');
  }
}

// ── AI contract assist ───────────────────────────────────────────────
$('#ai-fill-c')?.addEventListener('click', async () => {
  const prompt = $('#ai-prompt-c')?.value?.trim();
  const note = $('#ai-note-c');
  if (!prompt) { if (note) note.textContent = 'Paste a sample or description first.'; return; }
  const btn = $('#ai-fill-c');
  btn.disabled = true; btn.textContent = 'Drafting…';
  if (note) note.textContent = '';
  try {
    const res = await api('/assist/contract', jsonReq('POST', { prompt }));
    const c = res.contract;
    renderSchemaRows(c.schema_fields || [], 'schema-rows');
    renderRuleRows(c.quality_rules || [], 'rule-rows');
    if (c.slo_availability) $('#c-availability').value = c.slo_availability;
    if (c.slo_freshness) $('#c-freshness').value = c.slo_freshness;
    if (c.slo_max_latency) $('#c-latency').value = c.slo_max_latency;
    const n = (c.schema_fields || []).length;
    if (note) note.textContent = `✓ ${res.source === 'claude' ? 'Drafted by Claude.' : 'Drafted locally.'} ${n} field${n === 1 ? '' : 's'} inferred.`;
    toast('Contract drafted — review before saving');
  } catch (e) {
    if (note) note.textContent = 'Assistant error: ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = 'Draft with AI';
  }
});

// ── Input quality check / clarification ─────────────────────────────
let clarifyTimer = null;
let clarifyAllowed = true;    // false while panel is open or user skipped
let clarifyPending = false;   // waiting for API

function setupClarifyTriggers() {
  ['#name', '#description'].forEach(sel => {
    const el = $(sel);
    if (!el) return;
    el.addEventListener('blur', () => {
      if (!clarifyAllowed) return;
      clearTimeout(clarifyTimer);
      clarifyTimer = setTimeout(runClarifyCheck, 600);
    });
  });
}

async function runClarifyCheck(answers = '') {
  const name = $('#name')?.value.trim() || '';
  const description = $('#description')?.value.trim() || '';
  const domain = $('#domain')?.value.trim() || '';
  const source_systems = $('#source_systems')?.value || '';

  // Don't check empty form
  if (!name && !description) return;

  clarifyPending = true;
  try {
    const res = await api('/assist/clarify', jsonReq('POST', { name, description, domain, source_systems, answers }));

    if (!res.ok) {
      showClarifyPanel(res.message, res.questions);
    } else {
      hideClarifyPanel();
      // If AI returned improved fields, apply them
      if (res.improved && Object.keys(res.improved).length) {
        Object.entries(res.improved).forEach(([k, v]) => {
          const el = $(`#${k}`);
          if (el && v) { el.value = v; flash(el); }
        });
      }
    }
  } catch (e) { /* non-fatal */ }
  finally { clarifyPending = false; }
}

function showClarifyPanel(message, questions) {
  const panel = $('#clarify-panel');
  const msgEl = $('#clarify-message');
  const qBox = $('#clarify-questions');
  if (!panel || !msgEl || !qBox) return;

  msgEl.textContent = message;

  qBox.innerHTML = questions.map((q, i) => `
    <div>
      <label style="font-size:12px;font-weight:600;color:#374151;display:block;margin-bottom:4px;">${esc(q)}</label>
      <input type="text" id="clarify-q-${i}" class="search-input" placeholder="Your answer…" style="font-size:13px;" />
    </div>
  `).join('');

  panel.classList.remove('hidden');
  // focus first answer field
  const first = $(`#clarify-q-0`);
  if (first) setTimeout(() => first.focus(), 100);

  clarifyAllowed = false; // pause auto-checks while panel is open
}

function hideClarifyPanel() {
  $('#clarify-panel')?.classList.add('hidden');
  clarifyAllowed = true;
}

$('#clarify-submit')?.addEventListener('click', async () => {
  const questions = [...($('#clarify-questions')?.querySelectorAll('input') || [])];
  const answers = questions.map((inp, i) => {
    const label = inp.previousElementSibling?.textContent || `Q${i+1}`;
    return `${label}: ${inp.value.trim()}`;
  }).filter(a => !a.endsWith(': ')).join('\n');

  if (!answers.trim()) {
    const note = $('#clarify-note');
    if (note) note.textContent = 'Please answer at least one question.';
    return;
  }

  const btn = $('#clarify-submit');
  btn.disabled = true; btn.textContent = 'Evaluating…';
  const note = $('#clarify-note');
  if (note) note.textContent = '';

  // Merge answers back into visible fields where we can
  questions.forEach(inp => {
    const lbl = (inp.previousElementSibling?.textContent || '').toLowerCase();
    const val = inp.value.trim();
    if (!val) return;
    if (lbl.includes('domain') && !$('#domain')?.value) { $('#domain').value = val; flash($('#domain')); }
    if ((lbl.includes('source') || lbl.includes('system')) && !$('#source_systems')?.value) {
      $('#source_systems').value = val;
      renderTagItems('source-tags-wrap','source-tag-input','source-tag-add','source_systems',
        val.split(',').map(t=>t.trim()).filter(Boolean));
    }
    if (lbl.includes('name') && (!$('#name')?.value || $('#name').value.length < 5)) {
      $('#name').value = val; flash($('#name'));
    }
    if ((lbl.includes('description') || lbl.includes('contain') || lbl.includes('problem')) && !$('#description')?.value) {
      $('#description').value = val; flash($('#description'));
    }
  });

  clarifyAllowed = true;
  await runClarifyCheck(answers);

  btn.disabled = false; btn.textContent = '⚡ Submit answers';
  if ($('#clarify-panel').classList.contains('hidden')) {
    if (note) note.textContent = '';
    toast('Great! Form updated with your answers.');
  }
});

$('#clarify-skip')?.addEventListener('click', () => {
  hideClarifyPanel();
  clarifyAllowed = false; // don't re-trigger after skip
  toast('Proceeding — you can still improve the form later.');
});

// ── Suggestion chip renderer ─────────────────────────────────────────
function renderSuggestionChips(containerId, suggestions, onAdd) {
  const box = $(`#${containerId}`);
  if (!box) return;
  box.innerHTML = suggestions.map(s =>
    `<button type="button" class="btn ghost sm" data-sug="${esc(s)}" style="font-size:12px;padding:4px 10px;">${esc(s)} <span style="color:var(--orange)">+</span></button>`
  ).join('');
  box.querySelectorAll('[data-sug]').forEach(btn => {
    btn.addEventListener('click', () => { onAdd(btn.dataset.sug); btn.remove(); });
  });
}

// ── Improve description ──────────────────────────────────────────────
$('#improve-desc-btn')?.addEventListener('click', async () => {
  const desc = $('#description')?.value.trim();
  const note = $('#improve-desc-note');
  if (!desc) { if (note) note.textContent = 'Enter a description first.'; return; }
  const btn = $('#improve-desc-btn');
  btn.disabled = true; btn.textContent = 'Improving…';
  try {
    const res = await api('/assist/improve-description', jsonReq('POST', {
      description: desc,
      name: $('#name')?.value.trim() || '',
      domain: $('#domain')?.value.trim() || '',
    }));
    $('#description').value = res.improved;
    flash($('#description'));
    if (note) note.textContent = '✓ Improved.';
  } catch (e) { if (note) note.textContent = 'Error: ' + e.message; }
  finally { btn.disabled = false; btn.textContent = '✨ Improve with AI'; }
});

// ── Duplicate check (fires on step1-next) ───────────────────────────
async function checkDuplicates() {
  const name = $('#name')?.value.trim();
  const description = $('#description')?.value.trim();
  const domain = $('#domain')?.value.trim();
  const pid = $('#product_id')?.value;
  if (!name || pid) return; // skip for edits
  try {
    const res = await api('/assist/check-duplicate', jsonReq('POST', { name, description, domain, source_systems: '' }));
    const warn = $('#duplicate-warning');
    const chips = $('#duplicate-chips');
    if (res.similar?.length && warn && chips) {
      $('#duplicate-warning-text').textContent = res.warning || `⚠️ ${res.similar.length} similar product(s) already exist — consider reusing one:`;
      chips.innerHTML = res.similar.map(p =>
        `<button class="btn ghost sm" data-open-detail="${p.id}" style="font-size:12px;">
          ${esc(p.name)}${p.domain ? ` (${esc(p.domain)})` : ''} — ${esc(p.reason)}
        </button>`
      ).join('');
      chips.querySelectorAll('[data-open-detail]').forEach(b =>
        b.addEventListener('click', () => openDetail(allProducts.find(p => p.id == b.dataset.openDetail)))
      );
      warn.classList.remove('hidden');
    } else {
      $('#duplicate-warning')?.classList.add('hidden');
    }
  } catch (e) { /* non-fatal */ }
}

// ── Suggest sources ──────────────────────────────────────────────────
$('#suggest-sources-btn')?.addEventListener('click', async () => {
  const btn = $('#suggest-sources-btn');
  const note = $('#suggest-sources-note');
  btn.disabled = true; btn.textContent = 'Thinking…';
  try {
    const res = await api('/assist/suggest-sources', jsonReq('POST', {
      name: $('#name')?.value.trim() || '',
      domain: $('#domain')?.value.trim() || '',
      description: $('#description')?.value.trim() || '',
    }));
    renderSuggestionChips('sources-suggestions', res.suggestions, (val) => {
      const tags = getTagValues('source-tags-wrap', 'source_systems');
      if (!tags.includes(val)) {
        tags.push(val);
        renderTagItems('source-tags-wrap', 'source-tag-input', 'source-tag-add', 'source_systems', tags);
      }
    });
    if (note) note.textContent = `${res.suggestions.length} suggestions — click to add`;
  } catch (e) { if (note) note.textContent = 'Error: ' + e.message; }
  finally { btn.disabled = false; btn.textContent = '🤖 Suggest sources'; }
});

// ── Suggest tags ─────────────────────────────────────────────────────
$('#suggest-tags-btn')?.addEventListener('click', async () => {
  const btn = $('#suggest-tags-btn');
  const note = $('#suggest-tags-note');
  btn.disabled = true; btn.textContent = 'Thinking…';
  try {
    const res = await api('/assist/suggest-tags', jsonReq('POST', {
      name: $('#name')?.value.trim() || '',
      domain: $('#domain')?.value.trim() || '',
      description: $('#description')?.value.trim() || '',
      source_systems: $('#source_systems')?.value || '',
    }));
    renderSuggestionChips('tags-suggestions', res.suggestions, (val) => {
      const tags = getTagValues('tags-wrap', 'tags');
      if (!tags.includes(val)) {
        tags.push(val);
        renderTagItems('tags-wrap', 'tags-input', 'tags-add', 'tags', tags);
      }
    });
    if (note) note.textContent = `${res.suggestions.length} suggestions — click to add`;
  } catch (e) { if (note) note.textContent = 'Error: ' + e.message; }
  finally { btn.disabled = false; btn.textContent = '🤖 Suggest tags'; }
});

// Trigger duplicate check when moving from step 1 → 2
const origStep1Next = $('#step1-next');
origStep1Next?.addEventListener('click', checkDuplicates, true);

// ── Vega chat ────────────────────────────────────────────────────────
$('.chat-btn')?.addEventListener('click', () => {
  const panel = $('#vega-chat-panel');
  if (panel) {
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden')) $('#vega-input')?.focus();
  }
});
$('#vega-close')?.addEventListener('click', () => $('#vega-chat-panel')?.classList.add('hidden'));

async function sendVegaMessage() {
  const input = $('#vega-input');
  const msg = input?.value.trim();
  if (!msg || !currentProduct) return;
  input.value = '';
  appendVegaMessage('user', msg);
  $('#vega-send').disabled = true;
  try {
    const res = await api('/assist/chat', jsonReq('POST', { product_id: currentProduct.id, message: msg }));
    appendVegaMessage('vega', res.reply);
    if (res.note) { const n = $('#vega-note'); if (n) n.textContent = res.note; }
  } catch (e) {
    appendVegaMessage('vega', 'Sorry, I could not answer that right now.');
  } finally { $('#vega-send').disabled = false; }
}

function appendVegaMessage(role, text) {
  const box = $('#vega-messages');
  if (!box) return;
  const div = document.createElement('div');
  const isUser = role === 'user';
  div.style.cssText = isUser
    ? 'align-self:flex-end;background:var(--orange-light);border-radius:12px 12px 2px 12px;padding:8px 12px;max-width:80%;font-size:13px;word-break:break-word;'
    : 'align-self:flex-start;background:#f3f4f6;border-radius:12px 12px 12px 2px;padding:8px 12px;max-width:80%;font-size:13px;word-break:break-word;';
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

$('#vega-send')?.addEventListener('click', sendVegaMessage);
$('#vega-input')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendVegaMessage(); });

// ── Similar products on Detail ───────────────────────────────────────
async function loadSimilarProducts(product) {
  const bar = $('#similar-products-bar');
  const chips = $('#similar-products-chips');
  if (!bar || !chips || !product) return;
  bar.classList.add('hidden');
  try {
    const res = await api('/assist/check-duplicate', jsonReq('POST', {
      name: product.name,
      description: product.description || '',
      domain: product.domain || '',
      source_systems: product.source_systems || '',
    }));
    const others = (res.similar || []).filter(s => s.id !== product.id);
    if (!others.length) return;
    chips.innerHTML = others.map(s =>
      `<button class="btn ghost sm" data-open-similar="${s.id}" style="font-size:12px;">
        ${esc(s.name)}${s.domain ? ` · ${esc(s.domain)}` : ''}
      </button>`
    ).join('');
    chips.querySelectorAll('[data-open-similar]').forEach(b =>
      b.addEventListener('click', () => openDetail(allProducts.find(p => p.id == b.dataset.openSimilar)))
    );
    bar.classList.remove('hidden');
  } catch (e) { /* non-fatal */ }
}

bootstrap();
