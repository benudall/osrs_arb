'use strict';

const LS_KEY = 'osrs_arb_ui_v2';

const state = {
  levels: {},        // skill -> string ("" = no filter)
  skillFilter: {},   // skill -> bool (include in table; default true)
  f2pOnly: false,
  profitableOnly: false,
  ins: ['craft', 'buy'],       // visible acquisition column groups (craft = Craft, buy = Buy)
  routes: ['ge', 'ha', 'la'],  // visible route (sell) column groups
  filterLevels: true,
  search: '',
  searchMaterials: false,
};

let skills = [];
let rows = [];
let allRows = [];   // every evaluated row, before any filtering
let queryRows = []; // after the old server-side filters (skills/levels/f2p/search)
let meta = null;
let sortKey = 'best_net';
let sortDir = 'desc';
const expanded = new Set();

// static site data (baked by backend/scripts/bake_static.py)
let items = {};     // item id -> {name, image, limit, value, members}
let recipesData = [];
let natureId = null; // Nature rune item id (alchemy cost)

// live prices, polled straight from the wiki API (CORS-open)
const WIKI_BASE = 'https://prices.runescape.wiki/api/v1/osrs';
const store = new OSRSPriceStore();

const $ = (id) => document.getElementById(id);

const PRICES_ITEM_URL = 'https://prices.runescape.wiki/osrs/item/';
const WIKI_ITEM_URL = 'https://oldschool.runescape.wiki/w/';
const PRICES_FAVICON = 'https://www.google.com/s2/favicons?domain=prices.runescape.wiki&sz=16';
const WIKI_FAVICON = 'https://www.google.com/s2/favicons?domain=oldschool.runescape.wiki&sz=16';

function iconLink(href, src, title) {
  return `<a class="item-icon" href="${href}" target="_blank" rel="noopener" title="${title}">` +
    `<img src="${src}" alt="" width="13" height="13"></a>`;
}

function itemLinks(id, name, imageUrl) {
  let html = '';
  if (imageUrl) {
    html += `<img src="${imageUrl}" alt="" width="20" height="20" style="vertical-align: middle; margin-right: 4px;">`;
  }
  if (id !== null && id !== undefined) {
    html += `<span class="item-wrapper">${esc(name)}<span class="item-popover"><a href="${PRICES_ITEM_URL}${id}" target="_blank" rel="noopener"><img src="${PRICES_FAVICON}" alt=""> Prices</a><a href="${WIKI_ITEM_URL}${encodeURIComponent(name).replace(/%20/g, '_')}" target="_blank" rel="noopener"><img src="${WIKI_FAVICON}" alt=""> Wiki</a></span></span>`;
  } else {
    html += `<span class="item-wrapper">${esc(name)}</span>`;
  }
  return html;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// plain wiki article link (no item id needed)
function wikiLink(name) {
  return `<a href="${WIKI_ITEM_URL}${encodeURIComponent(name).replace(/%20/g, '_')}" target="_blank" rel="noopener">${esc(name)}</a>`;
}

function fmt(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('en-US');
}

function saveState() {
  localStorage.setItem(LS_KEY, JSON.stringify(state));
}

function loadState() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) Object.assign(state, JSON.parse(raw));
  } catch { /* ignore */ }
  // migrate legacy capitalized hiscores keys ("Smithing" -> "smithing")
  const norm = {};
  for (const [k, v] of Object.entries(state.levels || {})) {
    norm[String(k).toLowerCase()] = v;
  }
  state.levels = norm;
  // margin mode removed from the UI; conservative is the only mode
  delete state.mode;
  // hiscores lookup removed with the backend
  delete state.playerName;
  // old 'acq' was a row filter (better option); replaced by the In column toggle
  delete state.acq;
  if (!Array.isArray(state.ins)) state.ins = ['craft', 'buy'];
}

async function fetchJSON(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ---------- level inputs ----------

function renderLevels() {
  const wrap = $('levels');
  // keep the static player cell (first child), replace only the skill cells
  for (const el of [...wrap.querySelectorAll('.level-input:not(.player-cell)')]) el.remove();
  for (const s of skills) {
    const cell = document.createElement('div');
    cell.className = 'level-input';
    const span = document.createElement('span');
    const star = document.createElement('span');
    star.className = 'badge ' + (s.f2p ? 'f2p' : 'members');
    star.textContent = '★';
    star.title = s.f2p ? 'Has F2P recipes' : 'Members-only skill';
    span.append(star);
    span.append(document.createTextNode(s.skill));
    span.title = s.f2p ? 'Has F2P recipes' : 'Members-only skill';
    const input = document.createElement('input');
    input.type = 'number';
    input.min = '1';
    input.max = '99';
    input.placeholder = '—';
    input.value = state.levels[s.skill] ?? '';
    input.dataset.skill = s.skill;
    input.addEventListener('input', (e) => {
      state.levels[s.skill] = e.target.value;
      saveState();
      scheduleLoad();
    });
    const toggle = document.createElement('label');
    toggle.className = 'show-toggle';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = state.skillFilter[s.skill] !== false;
    cb.addEventListener('change', (e) => {
      state.skillFilter[s.skill] = e.target.checked;
      saveState();
      scheduleLoad();
    });
    toggle.append(cb, document.createTextNode('show'));
    cell.append(span, input, toggle);
    wrap.append(cell);
  }
}

// update values in the existing inputs (no rebuild -> keeps focus, keeps edits)
function fillLevelInputs() {
  for (const input of document.querySelectorAll('#levels input[data-skill]')) {
    input.value = state.levels[input.dataset.skill] ?? '';
  }
}

// ---------- data ----------

function computeSkills() {
  const by = new Map();
  for (const r of recipesData) {
    let s = by.get(r.skill);
    if (!s) {
      s = { skill: r.skill, count: 0, f2p: false };
      by.set(r.skill, s);
    }
    s.count++;
    if (!r.members) s.f2p = true;
  }
  return [...by.values()];
}

// the old server-side /api/recipes filters, now client-side
function queryFilter() {
  const active = new Set(skills.filter((s) => state.skillFilter[s.skill] !== false).map((s) => s.skill));
  if (skills.length && active.size === 0) return [];
  const levelMap = {};
  if (state.filterLevels) {
    for (const [k, v] of Object.entries(state.levels)) {
      const n = parseInt(v, 10);
      if (Number.isFinite(n) && n > 0) levelMap[k] = n;
    }
  }
  const q = state.search.trim().toLowerCase();
  const words = q ? q.split(/\s+/).filter(Boolean) : [];
  const out = [];
  for (const r of allRows) {
    if (active.size && active.size < skills.length) {
      if (!active.has(r.skill) && !(r.extra_skills || []).some((es) => active.has(es.skill))) continue;
    }
    if (state.f2pOnly && r.members) continue;
    if (state.filterLevels) {
      const lvl = levelMap[r.skill];
      if (lvl !== undefined && r.level > lvl) continue;
      if ((r.extra_skills || []).some((es) => levelMap[es.skill] !== undefined && levelMap[es.skill] < es.level)) continue;
    }
    if (words.length) {
      const parts = [r.product.name.toLowerCase()];
      if (state.searchMaterials) for (const m of r.materials) parts.push(m.name.toLowerCase());
      if (!words.every((w) => parts.join(' ').includes(w))) continue;
    }
    out.push(r);
  }
  return out;
}

let loadTimer = null;
function scheduleLoad() {
  clearTimeout(loadTimer);
  loadTimer = setTimeout(loadData, 350);
}

// client-side filters (profitableOnly) reapplied without a refetch
function applyFilters() {
  let out = queryRows;
  if (state.profitableOnly) out = out.filter((r) => bestNet(r) > 0);
  rows = out;
}

// re-evaluate all recipes against the current price store (no network)
function loadData() {
  if (!recipesData.length) return;
  const { rows: evaluated } = OSRSProfit.evaluateAll(recipesData, items, store, 'conservative');
  allRows = evaluated;
  queryRows = queryFilter();
  applyFilters();
  const nres = natureId != null ? store.resolve(natureId) : null;
  meta = {
    last_refresh: store.lastRefresh,
    alchemy_cost: nres?.high?.[0] ?? null,
    nature_rune_id: natureId,
    nature_rune_image: natureId != null ? (items[natureId]?.image ?? null) : null,
    nature_rune_vol: nres?.high_vol?.[0] ?? null,
  };
  renderMeta();
  renderTable();
}

let lastPoll = 0;
async function pollPrices(force = false) {
  const now = Date.now();
  if (!force && now - lastPoll < 10000) { loadData(); return; } // debounced: just re-render
  lastPoll = now;
  const banner = $('errorBanner');
  banner.hidden = true;
  try {
    const [latest, w5, w1] = await Promise.all([
      fetchJSON(WIKI_BASE + '/latest'),
      fetchJSON(WIKI_BASE + '/5m'),
      fetchJSON(WIKI_BASE + '/1h'),
    ]);
    store.updateLatest(latest);
    store.updateWindow(w5, '5m');
    store.updateWindow(w1, '1h');
    store.markRefreshed();
    loadData();
  } catch (e) {
    // keep whatever prices we have; surface the failure only if we have none
    console.warn('price refresh failed', e);
    if (!store.lastRefresh) {
      banner.textContent = 'could not reach the OSRS wiki prices API: ' + (e.message ?? e);
      banner.hidden = false;
    } else {
      loadData();
    }
  }
}

// ---------- rendering ----------

const COLS = [
  { key: 'product', label: 'Product', sortable: true,
    tip: 'Item crafted. Name links to its price page on the wiki.' },
  { key: 'materials', label: 'Materials', sortable: false,
    tip: 'Materials per craft, each at its cheapest acquisition price in gp (bought, or crafted if cheaper — ⚒ = crafted).' },
  { key: 'members', label: '★', sortable: false,
    tip: 'Gold star = Members recipe, silver star = Free-to-play.' },
  { key: 'skill', label: 'Skill', sortable: true,
    tip: 'Skill used to craft the product.' },
  { key: 'level', label: 'Lvl', sortable: true,
    tip: 'Skill level required for this recipe. Struck = requirement is above your set player/filter level for that skill.' },
  { key: 'xp', label: 'XP', sortable: true,
    tip: 'Experience gained per craft, from the OSRS wiki (0 = service actions like tanning, or the (unf) step of a potion).' },
  { key: 'cost', label: 'Craft', sortable: true,
    tip: 'Cheapest acquisition cost per craft = for each material the cheaper of buying or crafting it, x qty, plus fees (e.g. tanning).' },
  { key: 'buy', label: 'Buy', sortable: true,
    tip: 'Grand Exchange buy price of the product, per unit; (xN) below = units traded at that price in the 5m (or 1h) window. Craft/Buy comparisons use qty x this price vs Craft.' },
  { key: 'gross', label: 'Sell', sortable: true,
    tip: 'Grand Exchange sell revenue per craft = GE sell price x product qty; (xN) below = units traded at the sell price in the 5m (or 1h) window.' },
  { key: 'net', label: 'Sell Net', sortable: true,
    tip: 'GE sell-route profit per craft = gross - GE tax (2%, exempt <50 gp) - visible acquisition (Craft; or Buy x qty when the Craft column is hidden).' },
  { key: 'ha', label: 'HA', sortable: true,
    tip: 'High Level Alchemy payout per craft = product qty x floor(60% x static value).' },
  { key: 'ha_net', label: 'HA Net', sortable: true,
    tip: 'Alchemy-route profit per craft = HA - cheapest visible acquisition (Craft vs Buy x qty, per the In toggle) - alchemy cost (Nature rune instant-buy, live).' },
  { key: 'la', label: 'LA', sortable: true,
    tip: 'Low Level Alchemy payout per craft = product qty x floor(40% x static value).' },
  { key: 'la_net', label: 'LA Net', sortable: true,
    tip: 'Alchemy-route profit per craft = LA - cheapest visible acquisition (Craft vs Buy x qty, per the In toggle) - alchemy cost (Nature rune instant-buy, live).' },
  { key: 'best_net', label: 'Best\nNet', sortable: true,
    tip: 'Best route per craft = max over the enabled routes (Sell Net, HA Net, LA Net), each using only the visible acquisition (In toggle).' },
  { key: 'return', label: 'Return', sortable: true,
    tip: 'Return multiple = (Best Net + lowest visible acquisition) ÷ lowest visible acquisition (Craft vs Buy x qty). ≥1× = profit.' },
  { key: 'max_crafts_4h', label: '4h count', sortable: true,
    tip: 'Max crafts per 4 hours under Jagex GE buy limits (min over every material and the product). net/4h in the row detail.' },
];

const alch = (r, frac) => (r.product.value == null ? null : Math.floor(r.product.value * frac) * r.product.qty);
// acquisition cost per craft from the visible In columns only:
// both visible = cheaper of Craft vs Buy x qty; one visible = that one; none = null
const acqBase = (r) => {
  const c = inOn('craft') ? r.cost : null;
  const b = inOn('buy') && r.product.buy != null ? r.product.buy * r.product.qty : null;
  if (c != null && b != null) return Math.min(c, b);
  return c ?? b;
};
// Sell Net is Craft-based (as before) when Craft is visible; falls back to Buy x qty if Craft is hidden
const sellNet = (r) => {
  let base = inOn('craft') ? r.cost : null;
  if (base == null) base = acqBase(r);
  if (base == null) return null;
  return OSRSProfit.pyRound(r.gross - r.tax - base);
};
const alchNet = (r, frac) => {
  const a = alch(r, frac);
  const fee = meta && meta.alchemy_cost;
  const base = acqBase(r);
  if (a == null || fee == null || base == null) return null;
  return a - base - fee;
};
const bestNet = (r) => {
  const cands = [];
  if (routeOn('ge')) {
    const sn = sellNet(r);
    if (sn != null) cands.push(sn);
  }
  if (routeOn('ha')) {
    const h = alchNet(r, 0.6);
    if (h != null) cands.push(h);
  }
  if (routeOn('la')) {
    const l = alchNet(r, 0.4);
    if (l != null) cands.push(l);
  }
  return cands.length ? Math.max(...cands) : null;
};
// Return = (Best Net + lowest visible acquisition) ÷ lowest visible acquisition = payout ÷ cost
const returnMul = (r) => {
  const best = bestNet(r);
  if (best == null) return null;
  const base = acqBase(r);
  if (!base) return null; // free to acquire → ratio undefined
  return (best + base) / base;
};
const fmtMul = (v) => (v === null || v === undefined ? '—' : v.toFixed(2) + '×');

function cellValue(r, key) {
  if (key === 'product') return r.product.name;
  if (key === 'buy') return r.product.buy;
  if (key === 'ha') return alch(r, 0.6);
  if (key === 'la') return alch(r, 0.4);
  if (key === 'ha_net') return alchNet(r, 0.6);
  if (key === 'la_net') return alchNet(r, 0.4);
  if (key === 'net') return sellNet(r);
  if (key === 'best_net') return bestNet(r);
  if (key === 'return') return returnMul(r);
  return r[key];
}

function renderMeta() {
  if (!meta) return;
  const natureLink = meta.nature_rune_id ? itemLinks(meta.nature_rune_id, 'Nature rune', meta.nature_rune_image) : 'Nature rune';
  const bits = [
    meta.alchemy_cost == null
      ? `alchemy cost (${natureLink}): —`
      : `alchemy cost (${natureLink}): <span class="gp">${meta.alchemy_cost.toLocaleString()} gp</span>` +
        (meta.nature_rune_vol != null ? ` <span class="stock">(x${fmt(meta.nature_rune_vol)})</span>` : ''),
    'prices updated ' + (meta.last_refresh ? new Date(meta.last_refresh * 1000).toLocaleTimeString() : '—'),
  ];
  $('meta').innerHTML = bits.join(' · ');
}

// Two-row header: group th's span the (payout, net) leaf pairs below them.
const HEAD_GROUPS = [
  { id: 'ge', label: 'GE', keys: ['gross', 'net'] },
  { id: 'ha', label: 'HA', keys: ['ha', 'ha_net'] },
  { id: 'la', label: 'LA', keys: ['la', 'la_net'] },
];
const routeOf = new Map(HEAD_GROUPS.flatMap((g) => g.keys.map((k) => [k, g.id])));
const inOf = new Map([['cost', 'craft'], ['buy', 'buy']]); // column key -> In group id
const routeOn = (id) => state.routes.includes(id);
const inOn = (id) => state.ins.includes(id);
const visibleCols = () => COLS.filter((c) =>
  routeOf.has(c.key) ? routeOn(routeOf.get(c.key))
  : inOf.has(c.key) ? inOn(inOf.get(c.key))
  : true);

function renderHead() {
  const startOfGroup = new Map(HEAD_GROUPS.map((g) => [g.keys[0], g]));
  const inGroup = new Set(HEAD_GROUPS.flatMap((g) => g.keys));

  const tr1 = document.createElement('tr');
  const tr2 = document.createElement('tr');
  const leaf = (c) => {
    const th = document.createElement('th');
    th.textContent = c.label;
    if (c.tip) th.title = c.tip;
    if (c.key === 'best_net') th.style.whiteSpace = 'pre-line'; // label stacks vertically
    if (c.key === 'skill') th.style.textAlign = 'center';
    if (c.sortable) {
      th.className = 'sortable';
      th.dataset.key = c.key;
      if (sortKey === c.key) th.textContent += sortDir === 'asc' ? ' ▲' : ' ▼';
    }
    return th;
  };
  const GSEP_L = new Set(HEAD_GROUPS.map((g) => g.keys[0])); // left edge of each route group
  for (const c of visibleCols()) {
    if (inGroup.has(c.key)) {
      const g = startOfGroup.get(c.key);
      if (g) {
        const gh = document.createElement('th');
        gh.textContent = g.label;
        gh.colSpan = g.keys.length;
        gh.className = 'gsep';
        tr1.append(gh);
      }
      const lth = leaf(c);
      if (GSEP_L.has(c.key)) lth.classList.add('gsep');
      tr2.append(lth);
    } else {
      const th = leaf(c);
      th.rowSpan = 2;
      if (c.key === 'members' || c.key === 'cost' || (c.key === 'buy' && !inOn('craft'))) th.classList.add('gsep');
      if (c.key === 'best_net') th.classList.add('gsep');
      if (c.key === 'return') th.classList.add('gsep-r');
      tr1.append(th);
    }
  }
  $('thead').replaceChildren(tr1, tr2);
  // second header row must stick directly under the first, not at top: 0
  const h1 = tr1.offsetHeight;
  for (const th of tr2.children) th.style.top = h1 + 'px';
}

function detailHtml(r) {
  const sect = (label) => `<tr class="sect"><td colspan="9">${label}</td></tr>`;
  const val = (v, strike) => (v === null || v === undefined ? '<span class="dim">—</span>' : `<span class="gp${strike ? ' strike' : ''}">${fmt(v)}</span>`);
  const stockVal = (v) => (v === null || v === undefined ? '<span class="dim">—</span>' : `<span class="stock-val">${fmt(v)}</span>`);
  const row = (name, craftEach, buyEach, craftTotal, buyTotal, sellEach, sellTotal, tax, stock = null) => {
    const hasCraft = craftEach !== null && craftEach !== undefined;
    const craftHigher = hasCraft && buyEach !== null && buyEach !== undefined && craftEach > buyEach;
    return `<tr><td>${name}</td>` +
      `<td>${val(craftEach, craftHigher)}</td>` +
      `<td>${val(craftTotal, craftHigher)}</td>` +
      `<td>${val(buyEach, hasCraft && !craftHigher)}</td>` +
      `<td>${val(buyTotal, hasCraft && !craftHigher)}</td>` +
      `<td>${val(sellEach)}</td><td>${val(sellTotal)}</td><td>${val(tax)}</td><td>${stockVal(stock)}</td></tr>`;
  };
  const lines = [];

  lines.push('<table class="detail-table"><thead><tr><th>Name</th><th>Craft each</th><th>Craft total</th><th>Buy each</th><th>Buy total</th><th>Sell each</th><th>Sell total</th><th>Tax</th>' +
    '<th title="Grand Exchange stock at that price: units traded at that price point in the 5m (or 1h) window. 0 = no trades at that price in the window.">Stock</th></tr></thead><tbody>');

  if (r.tools && r.tools.length) {
    lines.push(sect('Tools'));
    for (const t of r.tools) {
      const name = t.id !== null && t.id !== undefined ? itemLinks(t.id, t.name, t.image_url) : esc(t.name);
      lines.push(row(name, null, t.buy, null, t.buy, null, null, null, t.buy_vol ?? null));
    }
  }
  if (r.facilities && r.facilities.length) {
    lines.push(sect('Facilities'));
    for (const f of r.facilities) {
      // some facility strings combine options ("Cooking range or fire") — link each part
      const parts = f.split(/\s+or\s+/).map(wikiLink).join(' or ');
      lines.push(row(parts, null, null, null, null, null, null, null));
    }
  }
  lines.push(sect('Materials'));
  let matsBuyTotal = 0;
  let matsCraftTotal = 0;
  for (const m of r.materials) {
    // struck = the more expensive acquisition (row() strikes craft when craft>buy, buy when craft<=buy & craft exists)
    const hasCraft = m.craft !== null && m.craft !== undefined;
    const craftStruck = hasCraft && m.craft > m.price;
    const buyStruck = hasCraft && !craftStruck;
    if (!buyStruck) matsBuyTotal += m.price * m.qty;        // buy total: only non-struck buy options
    if (hasCraft && !craftStruck) matsCraftTotal += m.craft * m.qty;  // craft total: only non-struck craft options
    const name = `${m.qty > 1 ? m.qty + '× ' : ''}${itemLinks(m.id, m.name, m.image_url)}`;
    lines.push(row(name, m.craft, m.price, hasCraft ? m.craft * m.qty : null, m.price * m.qty, null, null, null, m.vol ?? null));
  }
  if (r.materials.length > 1) {
    lines.push(row('<b>Materials total</b>', null, null, matsCraftTotal || null, matsBuyTotal || null, null, null, null));
  }
  lines.push(sect('Product'));
  const prodName = `${r.product.qty > 1 ? r.product.qty + '× ' : ''}${itemLinks(r.product.id, r.product.name, r.product.image_url)}`;
  const sellEach = Math.round(r.gross / r.product.qty);
  lines.push(row(prodName, null, null, null, null, sellEach, r.gross, r.tax, r.product.vol ?? null));
  lines.push('</tbody></table>');
  if (r.note) lines.push(`<div class="note">⚠ ${esc(r.note)}</div>`);
  return lines.join('');
}

function renderTable() {
  const sorted = [...rows].sort((a, b) => {
    const va = cellValue(a, sortKey);
    const vb = cellValue(b, sortKey);
    const cmp = va < vb ? -1 : va > vb ? 1 : 0;
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const tbody = $('tbody');
  tbody.replaceChildren();

  if (!sorted.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = visibleCols().length;
    td.className = 'empty';
    td.textContent = 'No rows — adjust filters or wait for the first price refresh.';
    tr.append(td);
    tbody.append(tr);
    return;
  }

  for (const r of sorted) {
    const tr = document.createElement('tr');
    tr.className = 'main-row' + (expanded.has(r.recipe_id) ? ' expanded' : '');
    tr.dataset.id = r.recipe_id;

    // product
    const tdP = document.createElement('td');
    const b = document.createElement('b');
    b.innerHTML = itemLinks(r.product.id, r.product.name, r.product.image_url);
    tdP.append(b);
    if (r.product.stale) {
      const st = document.createElement('span');
      st.className = 'stale';
      st.title = 'price from window average, latest stale';
      st.textContent = '≈';
      tdP.append(st);
    }
    tr.append(tdP);

    // materials — show cheapest acquisition per material (buy, or craft if cheaper)
    const matDesc = (m) => {
      const crafted = m.craft !== null && m.craft < m.price;
      const eff = crafted ? m.craft : m.price;
      return { eff, crafted };
    };
    const tdM = document.createElement('td');
    tdM.innerHTML = r.materials
      .map((m) => {
        const { eff, crafted } = matDesc(m);
        const qty = m.qty > 1 ? m.qty + '× ' : '';
        return `<div class="material-item"><span class="material-qty">${qty}</span>${itemLinks(m.id, m.name, m.image_url)}<small> (${fmt(eff)})</small></div>`;
      })
      .join('') + (r.fee > 0 ? `<div class="material-fee"><small> +${fmt(r.fee)} fee</small></div>` : '');
    tdM.title = r.materials
      .map((m) => {
        const { eff, crafted } = matDesc(m);
        return `${m.qty}x ${m.name} @ ${fmt(eff)} gp${crafted ? ' (crafted, cheaper than buying)' : ''}`;
      }).join('\n');
    tr.append(tdM);

    // members star
    const tdB = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = 'badge ' + (r.members ? 'members' : 'f2p');
    badge.textContent = '★';
    badge.title = r.members ? 'Members' : 'Free-to-play';
    tdB.classList.add('gsep');
    tdB.append(badge);
    tr.append(tdB);

    // skill required + level needed; struck = requirement above your player/filter level
    const tdS = document.createElement('td');
    const tdL = document.createElement('td');
    const shortNames = {
      'cooking': 'cook',
      'crafting': 'craft',
      'fletching': 'fletch',
      'herblore': 'herb',
      'magic': 'magic',
      'smithing': 'smith'
    };
    tdS.style.textAlign = 'center';
    tdL.style.textAlign = 'center';

    const num = (v, cls, f = fmt) => {
      const td = document.createElement('td');
      if (cls) td.className = cls;
      td.textContent = f(v);
      return td;
    };
    // value with the stock (units traded at that price) below it, white text
    const numStock = (v, vol, cls, f = fmt) => {
      const td = num(v, cls, f);
      if (v != null && vol != null) {
        const s = document.createElement('div');
        s.className = 'stock';
        s.textContent = `(x${fmt(vol)})`;
        td.append(s);
      }
      return td;
    };

    const addSkillRow = (skillName, level, playerLevel) => {
      const sDiv = document.createElement('div');
      sDiv.textContent = shortNames[skillName.toLowerCase()] ?? skillName;
      tdS.append(sDiv);

      const lDiv = document.createElement('div');
      lDiv.textContent = fmt(level);
      if (Number.isFinite(playerLevel) && level > playerLevel) {
        lDiv.classList.add('strike');
      }
      tdL.append(lDiv);
    };

    addSkillRow(r.skill, r.level, parseInt(state.levels[String(r.skill).toLowerCase()], 10));
    if (r.extra_skills) {
      for (const es of r.extra_skills) {
        addSkillRow(es.skill, es.level, parseInt(state.levels[String(es.skill).toLowerCase()], 10));
      }
    }

    tr.append(tdS, tdL);
    const haP = alch(r, 0.6);
    const laP = alch(r, 0.4);
    const haN = alchNet(r, 0.6);
    const laN = alchNet(r, 0.4);
    const bN = bestNet(r);
    const sn = sellNet(r);
    // struck = not the best route this row; best stays clean
    const netCls = (v) => `${v > 0 ? 'pos' : 'neg'}${v < bN ? ' strike' : ''}`;
    // payout struck when its route's net is not the best (matches the net cell)
    const payCls = (netV) => (netV != null && netV < bN ? 'gp strike' : 'gp');
    // struck = the higher of Craft vs Buy (unpicked acquisition); buy x qty = per craft
    // only when both In columns are visible — no comparison to show otherwise
    const pBuyTotal = r.product.buy != null ? r.product.buy * r.product.qty : null;
    const bothIn = inOn('craft') && inOn('buy');
    const craftCls = 'gp' + (bothIn && pBuyTotal != null && pBuyTotal < r.cost ? ' strike' : '');
    const buyCls = 'gp' + (bothIn && pBuyTotal != null && pBuyTotal > r.cost ? ' strike' : '');
    const cells = [num(r.xp)];
    if (inOn('craft')) cells.push(num(r.cost, craftCls + ' gsep'));
    if (inOn('buy')) cells.push(numStock(r.product.buy, r.product.buy_vol, buyCls + (inOn('craft') ? '' : ' gsep')));
    if (routeOn('ge')) cells.push(numStock(r.gross, r.product.vol, payCls(sn) + ' gsep'), num(sn, sn == null ? null : netCls(sn)));
    if (routeOn('ha')) cells.push(num(haP, payCls(haN) + ' gsep'), num(haN, haN == null ? null : netCls(haN)));
    if (routeOn('la')) cells.push(num(laP, payCls(laN) + ' gsep'), num(laN, laN == null ? null : netCls(laN)));
    const ret = returnMul(r);
    cells.push(num(bN, netCls(bN) + ' gsep'),
      num(ret, (ret == null ? null : ret >= 1 ? 'pos' : 'neg') + ' gsep-r', fmtMul),
      num(r.max_crafts_4h));
    tr.append(...cells);
    tbody.append(tr);

    if (expanded.has(r.recipe_id)) {
      const dtr = document.createElement('tr');
      dtr.className = 'detail-row';
      const td = document.createElement('td');
      td.colSpan = visibleCols().length;
      td.innerHTML = detailHtml(r);
      dtr.append(td);
      tbody.append(dtr);
    }
  }
}

// ---------- events ----------

$('thead').addEventListener('click', (e) => {
  const th = e.target.closest('th[data-key]');
  if (!th) return;
  const key = th.dataset.key;
  if (sortKey === key) {
    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey = key;
    sortDir = 'desc';
  }
  renderHead();
  renderTable();
});

$('tbody').addEventListener('click', (e) => {
  if (e.target.closest('a')) return; // item links: navigate, don't expand row
  const tr = e.target.closest('tr.main-row');
  if (!tr) return;
  const id = tr.dataset.id;
  if (expanded.has(id)) expanded.delete(id);
  else expanded.add(id);
  renderTable();
});

$('f2pOnly').addEventListener('change', (e) => { state.f2pOnly = e.target.checked; saveState(); scheduleLoad(); });
$('profitableOnly').addEventListener('change', (e) => { state.profitableOnly = e.target.checked; saveState(); scheduleLoad(); });
$('insFilter').addEventListener('change', (e) => {
  state.ins = [...e.target.selectedOptions].map((o) => o.value);
  saveState();
  // display-only toggle: no row filtering, just column visibility
  renderHead();
  renderTable();
});
$('routeFilter').addEventListener('change', (e) => {
  state.routes = [...e.target.selectedOptions].map((o) => o.value);
  saveState();
  // head + body in one synchronous pass: single paint, no misalignment gap
  applyFilters();
  renderHead();
  renderTable();
});
$('filterLevels').addEventListener('change', (e) => { state.filterLevels = e.target.checked; saveState(); scheduleLoad(); });
$('search').addEventListener('input', (e) => { state.search = e.target.value; saveState(); scheduleLoad(); });
$('searchMaterials').addEventListener('change', (e) => { state.searchMaterials = e.target.checked; saveState(); scheduleLoad(); });
$('refresh').addEventListener('click', () => pollPrices(true));

// ---------- init ----------

async function init() {
  loadState();
  $('f2pOnly').checked = state.f2pOnly;
  $('profitableOnly').checked = state.profitableOnly;
  for (const opt of $('insFilter').options) opt.selected = state.ins.includes(opt.value);
  for (const opt of $('routeFilter').options) opt.selected = state.routes.includes(opt.value);
  $('filterLevels').checked = state.filterLevels;
  $('search').value = state.search;
  $('searchMaterials').checked = state.searchMaterials;

  try {
    const data = await fetchJSON('data/recipes.json', { cache: 'no-cache' });
    items = data.items;
    recipesData = data.recipes;
    for (const [iid, info] of Object.entries(items)) {
      if (info.name === 'Nature rune') { natureId = parseInt(iid, 10); break; }
    }
    // fletching & herblore last, alphabetical otherwise
    const tail = (sk) => (sk.skill === 'fletching' || sk.skill === 'herblore') ? 1 : 0;
    skills = computeSkills().sort((a, b) => tail(a) - tail(b) || a.skill.localeCompare(b.skill));
    renderLevels();
  } catch (e) {
    $('errorBanner').textContent = `could not load data/recipes.json: ${e.message}`;
    $('errorBanner').hidden = false;
  }
  renderHead();
  loadData(); // empty price store -> rows appear after the first poll
  await pollPrices(true);
  // poll the wiki API every 60 s (prices only; recipes are static baked data)
  setInterval(() => { if (!document.hidden) pollPrices(true); }, 60000);
}

init();
