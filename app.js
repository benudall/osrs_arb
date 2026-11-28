'use strict';

const LS_KEY = 'osrs_arb_ui_v2';

const state = {
  levels: {},        // skill -> string ("" = no filter)
  skillFilter: {},   // skill -> bool (include in table; default true)
  f2pOnly: false,
  profitableOnly: false,
  ins: ['direct', 'mix', 'all', 'buy'],  // visible acquisition columns (craft direct/mix/all + buy)
  routes: ['ge', 'ha', 'la'],  // visible route (sell) column groups
  filterLevels: true,
  liquidGp: '',
  search: '',
  searchMaterials: false,
};

let skills = [];
let rows = [];
let allRows = [];   // every evaluated row, before any filtering
let queryRows = []; // after the old server-side filters (skills/levels/f2p/search)
let meta = null;
let craftRows = new Map(); // product item id -> evaluated recipe row (detail-table material recursion)
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
  if (!Array.isArray(state.ins)) state.ins = ['direct', 'mix', 'all', 'buy'];
  // the old single 'craft' In option split into the direct/mix/all craft columns;
  // 'imm' (briefly 'Craft Immediate') renamed to 'direct'
  if (state.ins.some((v) => v === 'craft' || v === 'imm')) {
    state.ins = [...new Set(state.ins.flatMap(
      (v) => (v === 'craft' ? ['direct', 'mix', 'all'] : v === 'imm' ? ['direct'] : [v])))];
  }
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
  // product item id -> the evaluated row behind its cheapest per-unit craft cost
  // (same recipe the Craft column's material prices come from); lets the detail
  // table expand materials that are themselves products of other recipes
  const bestCraft = new Map();
  const firstRow = new Map();
  for (const row of evaluated) {
    if (!firstRow.has(row.product.id)) firstRow.set(row.product.id, row);
    if (row.cost != null && row.product.qty >= 1) {
      const cur = bestCraft.get(row.product.id);
      if (!cur || row.cost / row.product.qty < cur.cost / cur.product.qty) bestCraft.set(row.product.id, row);
    }
  }
  craftRows = new Map([...firstRow].map(([pid, row]) => [pid, bestCraft.get(pid) ?? row]));
  queryRows = queryFilter();
  applyFilters();
  const nres = natureId != null ? store.resolve(natureId) : null;
  // newest trade timestamp across all items: game live -> a few min old max;
  // frozen while polls still succeed -> servers likely in maintenance
  let latestTs = 0;
  for (const d of Object.values(store.latest)) {
    if (d.high_ts > latestTs) latestTs = d.high_ts;
    if (d.low_ts > latestTs) latestTs = d.low_ts;
  }
  meta = {
    last_refresh: store.lastRefresh,
    latest_ts: latestTs || null,
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
  { key: 'product', label: 'Products', sortable: true,
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
  { key: 'cost_direct', label: 'Direct', sortable: true,
    tip: 'Craft Direct: buy every material at GE prices, craft only the main product = Σ material buy price x qty + fees (e.g. tanning). * = some materials have no GE price — covers priced parts only.' },
  { key: 'cost', label: 'Mix', sortable: true,
    tip: 'Craft Mix: cheapest combination of buying and crafting = for each material the cheaper of buying it or crafting it (recursive; ⚒ = crafted in the Materials column), x qty, plus fees (e.g. tanning). * = some materials have no GE price — covers priced parts only.' },
  { key: 'cost_all', label: 'All', sortable: true,
    tip: 'Craft All: buy only the root materials at the deepest recursion level and craft every intermediate. Craftable materials are always crafted — even when buying them would be cheaper, that is the scenario this column prices; non-craftable materials are bought. * = some root materials have no GE price — covers priced parts only.' },
  { key: 'buy', label: 'Buy', sortable: true,
    tip: 'Grand Exchange buy price of the product, per unit; (xN) below = units traded at that price in the 5m (or 1h) window. Craft/Buy comparisons use qty x this price vs Craft.' },
  { key: 'gross', label: 'Sell', sortable: true,
    tip: 'Grand Exchange sell revenue per craft = GE sell price x product qty; (xN) below = units traded at the sell price in the 5m (or 1h) window.' },
  { key: 'net', label: 'Sell Net', sortable: true,
    tip: 'GE sell-route profit per craft = gross - GE tax (2%, exempt <50 gp) - cheapest visible acquisition (In toggle).' },
  { key: 'ha', label: 'HA', sortable: true,
    tip: 'High Level Alchemy payout per craft = product qty x floor(60% x static value); (N) below = payout minus Nature rune instant-buy price (live).' },
  { key: 'ha_net', label: 'HA Net', sortable: true,
    tip: 'Alchemy-route profit per craft = HA - cheapest visible acquisition (Craft Direct/Mix/All vs Buy x qty, per the In toggle) - alchemy cost (Nature rune instant-buy, live).' },
  { key: 'la', label: 'LA', sortable: true,
    tip: 'Low Level Alchemy payout per craft = product qty x floor(40% x static value); (N) below = payout minus Nature rune instant-buy price (live).' },
  { key: 'la_net', label: 'LA Net', sortable: true,
    tip: 'Alchemy-route profit per craft = LA - cheapest visible acquisition (Craft Direct/Mix/All vs Buy x qty, per the In toggle) - alchemy cost (Nature rune instant-buy, live).' },
  { key: 'best_net', label: 'Best\nNet', sortable: true,
    tip: 'Best route per craft = max over the enabled routes (Sell Net, HA Net, LA Net), each using only the visible acquisition (In toggle).' },
  { key: 'return', label: 'Return', sortable: true,
    tip: 'Return multiple = (Best Net + lowest visible acquisition) ÷ lowest visible acquisition (Craft vs Buy x qty). ≥1× = profit.' },
  { key: 'max_gp', label: 'Max\nNet', sortable: true,
    tip: 'Max net from liquid gold: top = Best Net x crafts affordable with Liquid gp (÷ cheapest visible acquisition, Craft vs Buy x qty); (xN) below = craft count.' },
  { key: 'max_crafts_4h', label: '4h count', sortable: true,
    tip: 'Max crafts per 4 hours under Jagex GE buy limits (min over every material and the product). net/4h in the row detail.' },
];

const alch = (r, frac) => (r.product.value == null ? null : Math.floor(r.product.value * frac) * r.product.qty);
// all nets use the cheapest visible acquisition (In toggle): min of the visible
// craft columns and Buy x qty; none visible = null
const acqBase = (r) => {
  const opts = [];
  if (inOn('direct') && r.cost_direct != null) opts.push(r.cost_direct);
  if (inOn('mix') && r.cost != null) opts.push(r.cost);
  if (inOn('all') && r.cost_all != null) opts.push(r.cost_all);
  const b = inOn('buy') && r.product.buy != null ? r.product.buy * r.product.qty : null;
  if (b != null) opts.push(b);
  return opts.length ? Math.min(...opts) : null;
};
// Sell Net = GE sell-route profit per craft = gross - tax - cheapest visible acquisition
const sellNet = (r) => {
  if (r.gross == null) return null;
  const base = acqBase(r);
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

// Liquid gp as a positive number, or null when unset/invalid
const liquidGpNum = () => {
  const n = parseFloat(state.liquidGp);
  return Number.isFinite(n) && n > 0 ? n : null;
};
// Max gp = crafts affordable with Liquid gp (÷ cheapest visible acquisition) x Best Net
const maxCrafts = (r) => {
  const lg = liquidGpNum();
  const base = acqBase(r);
  if (lg == null || base == null || base <= 0) return null;
  return Math.floor(lg / base);
};
const maxGp = (r) => {
  const best = bestNet(r);
  const n = maxCrafts(r);
  if (best == null || n == null) return null;
  return best * n;
};

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
  if (key === 'max_gp') return maxGp(r);
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
    'last refresh ' + (meta.last_refresh ? new Date(meta.last_refresh * 1000).toLocaleTimeString() : '—'),
  ];
  // newest trade age: red past 10 min while refreshes keep succeeding = likely maintenance
  const LATE_SECS = 600;
  const age = meta.latest_ts ? Date.now() / 1000 - meta.latest_ts : null;
  const late = age != null && age > LATE_SECS;
  const ageBit = meta.latest_ts
    ? ` <a class="latest-age${late ? ' late' : ''}" href="https://oldschool.runescape.com/game-status" target="_blank" rel="noopener" title="Trade timestamps from the OSRS wiki prices API. Opens the Jagex game status page.${late ? ' No trades for ' + Math.floor(age / 60) + ' min while price refreshes still succeed — RuneScape may be under maintenance.' : ''}">(${Math.floor(age / 60)}m old)</a>`
    : '';
  bits.push(`latest prices <span${late ? ' class="late"' : ''}>${meta.latest_ts ? new Date(meta.latest_ts * 1000).toLocaleTimeString() : '—'}${ageBit}</span>`);
  $('meta').innerHTML = bits.join(' · ');
}

// Two-row header: group th's span the (payout, net) leaf pairs below them.
const HEAD_GROUPS = [
  { id: 'craft', label: 'Craft', keys: ['cost_direct', 'cost', 'cost_all'], toggle: 'ins' },
  { id: 'ge', label: 'GE', keys: ['gross', 'net'], toggle: 'route' },
  { id: 'ha', label: 'HA', keys: ['ha', 'ha_net'], toggle: 'route' },
  { id: 'la', label: 'LA', keys: ['la', 'la_net'], toggle: 'route' },
];
const groupOf = new Map(HEAD_GROUPS.flatMap((g) => g.keys.map((k) => [k, g])));
const inOf = new Map([['cost_direct', 'direct'], ['cost', 'mix'], ['cost_all', 'all'], ['buy', 'buy']]); // column key -> In group id
const routeOn = (id) => state.routes.includes(id);
const inOn = (id) => state.ins.includes(id);
// column visible? craft-group leaves toggle individually via In, route-group
// leaves as a whole via Out, standalone In columns (buy) via their In option
const visOf = (k) => {
  const g = groupOf.get(k);
  if (!g) return inOf.has(k) ? inOn(inOf.get(k)) : true;
  return g.toggle === 'ins' ? inOn(inOf.get(k)) : routeOn(g.id);
};
const visibleCols = () => COLS.filter((c) => visOf(c.key));

function renderHead() {
  const inGroup = new Set(HEAD_GROUPS.flatMap((g) => g.keys));
  // group header goes above the group's first VISIBLE leaf (the first key may
  // be toggled off); colSpan = count of the group's visible leaves
  const firstVisible = new Map();
  for (const g of HEAD_GROUPS) {
    const vk = g.keys.filter(visOf);
    if (vk.length) firstVisible.set(vk[0], { g, span: vk.length });
  }

  const tr1 = document.createElement('tr');
  const tr2 = document.createElement('tr');
  const anyCraft = inOn('direct') || inOn('mix') || inOn('all');
  // does a group's left edge need its own separator? the XP column's right
  // border already separates the info block from the acquisition block, so the
  // craft group never does; GE sits next to Buy (or the XP border when Buy is
  // hidden); HA/LA always sit next to another route group
  const gsepL = (g) => (g.id === 'craft' ? false : g.id === 'ge' ? inOn('buy') : true);
  const leaf = (c) => {
    const th = document.createElement('th');
    th.textContent = c.key === 'product' ? `Products (x${rows.length})` : c.label;
    if (c.tip) th.title = c.tip;
    if (c.key === 'best_net' || c.key === 'max_gp') th.style.whiteSpace = 'pre-line'; // label stacks vertically
    if (c.key === 'skill') th.style.textAlign = 'center';
    if (c.sortable) {
      th.className = 'sortable';
      th.dataset.key = c.key;
      if (sortKey === c.key) th.textContent += sortDir === 'asc' ? ' ▲' : ' ▼';
    }
    return th;
  };
  for (const c of visibleCols()) {
    if (inGroup.has(c.key)) {
      const fg = firstVisible.get(c.key);
      if (fg) {
        const gh = document.createElement('th');
        gh.textContent = fg.g.label;
        gh.colSpan = fg.span;
        if (gsepL(fg.g)) gh.className = 'gsep';
        tr1.append(gh);
      }
      const lth = leaf(c);
      if (fg && gsepL(fg.g)) lth.classList.add('gsep');
      tr2.append(lth);
    } else {
      const th = leaf(c);
      th.rowSpan = 2;
      if (c.key === 'members' || (c.key === 'buy' && anyCraft)) th.classList.add('gsep');
      if (c.key === 'xp') th.classList.add('gsep-r');
      if (c.key === 'best_net') th.classList.add('gsep');
      if (c.key === 'max_gp') th.classList.add('gsep-r');
      tr1.append(th);
    }
  }
  $('thead').replaceChildren(tr1, tr2);
  // second header row must stick directly under the first, not at top: 0
  const h1 = tr1.offsetHeight;
  for (const th of tr2.children) th.style.top = h1 + 'px';
}

function detailHtml(r) {
  const INDENT = 16; // px of name-cell indent per recursion level
  const stockTip = 'Grand Exchange stock at that price: units traded at that price point in the 5m (or 1h) window. 0 = no trades at that price in the window.';

  // Materials that are themselves products of recipes are expanded in rows
  // ABOVE the material: the material's recipe opens as indented sub-rows, and
  // the material's own row below them doubles as the total of that block
  // (same columns as the product row). craftRows maps product item id -> the
  // evaluated recipe row behind its Craft price (see loadData); the product-id
  // chain guards against recipe loops. Each node also remembers the buy price
  // of the product it goes into, so a sub-material that costs more than that
  // product is struck out (its whole acquisition path is dominated).
  const buildNode = (mat, chain, parentPrice, parentName) => {
    const sub = craftRows.get(mat.id) ?? null;
    const node = { mat, sub, children: [], fee: 0, parentPrice: parentPrice ?? null, parentName: parentName ?? null };
    if (!sub || chain.has(mat.id)) return node; // not craftable, or would loop
    const next = new Set(chain);
    next.add(mat.id);
    node.children = sub.materials.map((m) => buildNode(m, next, mat.price, mat.name));
    node.fee = sub.fee || 0;
    return node;
  };

  const topNodes = r.materials.map((m) => buildNode(m, new Set([r.product.id])));

  const val = (v, strike) => (v === null || v === undefined || Number.isNaN(v)
    ? '<span class="dim">—</span>'
    : `<span class="gp${strike ? ' strike' : ''}">${fmt(v)}</span>`);
  const stockVal = (v) => (v === null || v === undefined ? '<span class="dim">—</span>' : `<span class="stock-val">${fmt(v)}</span>`);
  const matName = (m) => `${m.qty > 1 ? m.qty + '× ' : ''}${itemLinks(m.id, m.name, m.image_url)}`;
  const indent = (depth) => (depth > 0 ? ` style="padding-left:${depth * INDENT}px"` : '');

  // one material row; a row with children (a craftable material) doubles as
  // the total of the rows above it, so it gets the totals styling.
  // Struck = the more expensive acquisition: craft vs buy within the row, and
  // (for expanded sub-materials) the whole row when its cheapest acquisition
  // costs more than the product it goes into.
  const matRow = (node, depth) => {
    const m = node.mat;
    const isParent = node.children.length > 0;
    const hasCraft = m.craft !== null && m.craft !== undefined;
    const craftHigher = hasCraft && m.price !== null && m.price !== undefined && m.craft > m.price;
    const craftChosen = hasCraft && (m.price == null || m.craft < m.price);
    const chosen = craftChosen ? m.craft : m.price;
    const dominated = node.parentPrice != null && chosen != null && chosen > node.parentPrice;
    const strikeCraft = (hasCraft && craftHigher) || (dominated && craftChosen);
    const strikeBuy = (hasCraft && !craftHigher) || (dominated && !craftChosen);
    let tip = '';
    if (isParent) {
      tip = ` title="Crafted: ${esc(node.sub.materials.map((sm) => `${sm.qty}× ${sm.name}`).join(' + '))} → ${node.sub.product.qty}× ${esc(m.name)} (per craft) — total of the rows above"`;
    } else if (dominated) {
      tip = ` title="${fmt(chosen)} gp — more expensive than ${esc(node.parentName)} (${fmt(node.parentPrice)} gp)"`;
    }
    const cls = depth === 0 ? ` class="hl${isParent ? ' totals' : ''}"` : isParent ? ' class="totals"' : '';
    return `<tr${cls}><td${indent(depth)}${tip}>${matName(m)}</td>` +
      `<td>${val(m.craft, strikeCraft)}</td>` +
      `<td>${val(hasCraft ? m.craft * m.qty : null, strikeCraft)}</td>` +
      `<td>${val(m.price, strikeBuy)}</td>` +
      `<td>${val(m.price != null ? m.price * m.qty : null, strikeBuy)}</td>` +
      `<td>${val(null)}</td><td>${val(null)}</td><td>${val(null)}</td>` +
      `<td>${stockVal(m.vol)}</td></tr>`;
  };

  // sub-recipe fee, one more indented row above the total row
  const feeRow = (fee, depth) =>
    `<tr><td${indent(depth)}><span class="dim">+ fee</span></td>` +
    `<td>${val(null)}</td><td>${val(fee)}</td><td>${val(null)}</td><td>${val(null)}</td>` +
    `<td>${val(null)}</td><td>${val(null)}</td><td>${val(null)}</td><td>${val(null)}</td></tr>`;

  // post-order: a node's expansion renders above its own (total) row
  const emitNode = (node, depth, out) => {
    for (const c of node.children) emitNode(c, depth + 1, out);
    if (node.fee > 0) out.push(feeRow(node.fee, depth + 1));
    out.push(matRow(node, depth));
  };

  const lines = [];

  // tools & facilities as a plain note above the table (no price columns)
  const notes = [];
  if (r.tools && r.tools.length) {
    notes.push('Tools: ' + r.tools.map((t) => (t.id !== null && t.id !== undefined ? itemLinks(t.id, t.name, t.image_url) : esc(t.name))).join(', '));
  }
  if (r.facilities && r.facilities.length) {
    // some facility strings combine options ("Cooking range or fire") — link each part
    notes.push('Facilities: ' + r.facilities.map((f) => f.split(/\s+or\s+/).map(wikiLink).join(' or ')).join(', '));
  }
  if (notes.length) lines.push(`<div class="hint">${notes.join(' · ')}</div>`);

  lines.push('<table class="detail-table"><thead><tr><th>Name</th><th>Mix each</th><th>Mix total</th><th>Buy each</th><th>Buy total</th><th>Sell each</th><th>Sell total</th><th>Tax</th>' +
    `<th title="${stockTip}">Stock</th></tr></thead><tbody>`);

  const sect = (label) => `<tr class="sect"><td colspan="9">${label}</td></tr>`;

  lines.push(sect('Materials'));
  for (const n of topNodes) emitNode(n, 0, lines);
  if (r.materials.length > 1) {
    let matsBuyTotal = 0;
    let matsCraftTotal = 0;
    for (const m of r.materials) {
      // struck = the more expensive acquisition (excluded from the totals)
      const hasCraft = m.craft !== null && m.craft !== undefined;
      const craftStruck = hasCraft && m.craft > m.price;
      const buyStruck = hasCraft && !craftStruck; // buy struck when craft is the cheaper pick
      if (!buyStruck && m.price != null) matsBuyTotal += m.price * m.qty;        // buy total: only non-struck buy options
      if (hasCraft && !craftStruck && m.craft != null) matsCraftTotal += m.craft * m.qty;  // craft total: only non-struck craft options
    }
    lines.push('<tr class="totals hl"><td><b>Materials total</b></td>' +
      `<td>${val(null)}</td><td>${val(matsCraftTotal || null)}</td><td>${val(null)}</td><td>${val(matsBuyTotal || null)}</td>` +
      `<td>${val(null)}</td><td>${val(null)}</td><td>${val(null)}</td><td>${stockVal(null)}</td></tr>`);
  }
  lines.push(sect('Product'));
  const prodName = `${r.product.qty > 1 ? r.product.qty + '× ' : ''}${itemLinks(r.product.id, r.product.name, r.product.image_url)}`;
  const sellEach = r.gross == null ? null : Math.round(r.gross / r.product.qty);
  lines.push(`<tr class="hl"><td>${prodName}</td><td>${val(null)}</td><td>${val(null)}</td><td>${val(null)}</td><td>${val(null)}</td>` +
    `<td>${val(sellEach)}</td><td>${val(r.gross)}</td><td>${val(r.tax)}</td><td>${stockVal(r.product.vol ?? null)}</td></tr>`);
  lines.push('</tbody></table>');
  if (r.note) lines.push(`<div class="note">⚠ ${esc(r.note)}</div>`);
  return lines.join('');
}

function renderTable() {
  // keep the product header count in sync when filters change without a head re-render
  const pth = document.querySelector('#thead th[data-key="product"]');
  if (pth) pth.textContent = `Products (x${rows.length})` + (sortKey === 'product' ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '');

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
    // value with (value - Nature rune price) below it, gold text
    const numNet = (v, cls) => {
      const td = num(v, cls);
      const fee = meta && meta.alchemy_cost;
      if (v != null && fee != null) {
        const s = document.createElement('div');
        s.className = 'gp small';
        s.textContent = `(${fmt(v - fee)})`;
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
    // struck = a cheaper visible acquisition exists (any In column); buy x qty = per craft
    const pBuyTotal = r.product.buy != null ? r.product.buy * r.product.qty : null;
    const acqVals = [];
    if (inOn('direct') && r.cost_direct != null) acqVals.push(r.cost_direct);
    if (inOn('mix') && r.cost != null) acqVals.push(r.cost);
    if (inOn('all') && r.cost_all != null) acqVals.push(r.cost_all);
    if (inOn('buy') && pBuyTotal != null) acqVals.push(pBuyTotal);
    const bestAcq = acqVals.length ? Math.min(...acqVals) : null;
    const acqCls = (v) => 'gp' + (bestAcq != null && v != null && v > bestAcq ? ' strike' : '');
    const anyCraft = inOn('direct') || inOn('mix') || inOn('all');
    // craft cost cell with the unpriced (*) marker when its variant is partial/unavailable
    const costCell = (v, incomplete, cls, why) => {
      const td = num(v, cls);
      if (incomplete) {
        const star = document.createElement('span');
        star.className = 'unpriced';
        star.textContent = '*';
        star.title = why;
        td.append(star);
      }
      return td;
    };
    const cells = [num(r.xp, 'gsep-r')];
    if (inOn('direct')) cells.push(costCell(r.cost_direct, r.direct_incomplete, acqCls(r.cost_direct),
      'Some materials have no GE price — they cannot be bought, so Craft Direct is unavailable.'));
    if (inOn('mix')) cells.push(costCell(r.cost, r.cost_incomplete, acqCls(r.cost),
      'Some materials have no GE price — cost covers priced parts only.'));
    if (inOn('all')) cells.push(costCell(r.cost_all, r.all_incomplete, acqCls(r.cost_all),
      'Some materials have no GE price — cost covers priced parts only.'));
    if (inOn('buy')) cells.push(numStock(r.product.buy, r.product.buy_vol, acqCls(pBuyTotal) + (anyCraft ? ' gsep' : '')));
    if (routeOn('ge')) cells.push(numStock(r.gross, r.product.vol, payCls(sn) + (inOn('buy') ? ' gsep' : '')), num(sn, sn == null ? null : netCls(sn)));
    if (routeOn('ha')) cells.push(numNet(haP, payCls(haN) + ' gsep'), num(haN, haN == null ? null : netCls(haN)));
    if (routeOn('la')) cells.push(numNet(laP, payCls(laN) + ' gsep'), num(laN, laN == null ? null : netCls(laN)));
    const ret = returnMul(r);
    // Max Net: Best Net x crafts affordable with Liquid gp, (xN) count below
    const mgCell = () => {
      const td = document.createElement('td');
      const n = maxCrafts(r);
      const total = maxGp(r);
      if (n == null || total == null) {
        td.textContent = '—';
        td.classList.add('gsep-r');
        return td;
      }
      td.classList.add('gsep-r');
      const gp = document.createElement('div');
      gp.className = 'gp';
      gp.textContent = fmt(total);
      td.append(gp);
      const s = document.createElement('div');
      s.className = 'stock';
      s.textContent = `(x${fmt(n)})`;
      td.append(s);
      return td;
    };
    cells.push(num(bN, (bN == null ? null : netCls(bN)) + ' gsep'),
      num(ret, (ret == null ? null : ret >= 1 ? 'pos' : 'neg'), fmtMul),
      mgCell(),
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
$('liquidGp').addEventListener('input', (e) => { state.liquidGp = e.target.value; saveState(); scheduleLoad(); });
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
  $('liquidGp').value = state.liquidGp;
  $('search').value = state.search;
  $('searchMaterials').checked = state.searchMaterials;

  try {
    const [index, itemsDoc] = await Promise.all([
      fetchJSON('data/recipes/index.json', { cache: 'no-cache' }),
      fetchJSON('data/items.json', { cache: 'no-cache' }),
    ]);
    const skillLists = await Promise.all(
      index.skills.map((s) => fetchJSON(`data/recipes/${s}.json`, { cache: 'no-cache' }))
    );
    items = itemsDoc.items;
    recipesData = skillLists.flat();
    for (const [iid, info] of Object.entries(items)) {
      if (info.name === 'Nature rune') { natureId = parseInt(iid, 10); break; }
    }
    // fletching & herblore last, alphabetical otherwise
    const tail = (sk) => (sk.skill === 'fletching' || sk.skill === 'herblore') ? 1 : 0;
    skills = computeSkills().sort((a, b) => tail(a) - tail(b) || a.skill.localeCompare(b.skill));
    renderLevels();
  } catch (e) {
    $('errorBanner').textContent = `could not load baked data (data/items.json + data/recipes/): ${e.message}`;
    $('errorBanner').hidden = false;
  }
  renderHead();
  loadData(); // empty price store -> rows appear after the first poll
  await pollPrices(true);
  // poll the wiki API every 60 s (prices only; recipes are static baked data)
  setInterval(() => { if (!document.hidden) pollPrices(true); }, 60000);
}

init();
