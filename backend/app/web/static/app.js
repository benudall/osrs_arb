'use strict';

const LS_KEY = 'osrs_arb_ui_v2';

const state = {
  levels: {},        // skill -> string ("" = no filter)
  skillFilter: {},   // skill -> bool (include in table; default true)
  f2pOnly: false,
  profitableOnly: false,
  acq: [],
  routes: ['ge', 'ha', 'la'],  // visible route column groups
  filterLevels: true,
  playerName: '',
  search: '',
  searchMaterials: false,
};

let skills = [];
let rows = [];
let allRows = [];  // unfiltered server response; applyFilters() -> rows
let meta = null;
let sortKey = 'best_net';
let sortDir = 'desc';
const expanded = new Set();

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
  // migrate legacy single-value acq ('any'|'craft'|'buy') to array
  if (typeof state.acq === 'string') {
    state.acq = state.acq === 'any' ? [] : [state.acq];
  }
}

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
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
    span.textContent = s.skill;
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

async function fetchPlayer() {
  const name = state.playerName.trim();
  const err = $('playerError');
  err.hidden = true;
  if (!name) return;
  $('fetchPlayer').disabled = true;
  try {
    const res = await api(`/api/hiscores?player=${encodeURIComponent(name)}`);
    for (const [skill, level] of Object.entries(res.skills)) {
      state.levels[skill.toLowerCase()] = String(level);
    }
    saveState();
    fillLevelInputs();
    scheduleLoad();
  } catch (e) {
    err.textContent = `hiscores: ${e.message}`;
    err.hidden = false;
  } finally {
    $('fetchPlayer').disabled = false;
  }
}

// ---------- data ----------

function buildQuery() {
  const p = new URLSearchParams();
  const active = skills.filter((s) => state.skillFilter[s.skill] !== false);
  if (active.length && active.length < skills.length) {
    p.set('skills', active.map((s) => s.skill).join(','));
  }
  p.set('mode', 'conservative');
  if (state.f2pOnly) p.set('f2p_only', 'true');
  if (state.filterLevels) {
    const levels = Object.entries(state.levels)
      .map(([k, v]) => [k, parseInt(v, 10)])
      .filter(([, v]) => Number.isFinite(v) && v > 0)
      .map(([k, v]) => `${k}:${v}`);
    if (levels.length) p.set('levels', levels.join(','));
  }
  const q = state.search.trim();
  if (q) {
    p.set('q', q);
    if (state.searchMaterials) p.set('include_materials', 'true');
  }
  return p.toString();
}

let loadTimer = null;
let loadSeq = 0;
function scheduleLoad() {
  clearTimeout(loadTimer);
  loadTimer = setTimeout(loadData, 350);
}

// client-side filters (routes/profitableOnly/acq) reapplied without a refetch
function applyFilters() {
  let out = allRows;
  if (state.profitableOnly) out = out.filter((r) => bestNet(r) > 0);
  if (state.acq.length) {
    out = out.filter((r) => {
      if (r.product.buy == null) return false;
      const b = r.product.buy * r.product.qty; // per craft: qty units
      return (state.acq.includes('craft') && r.cost < b) || (state.acq.includes('buy') && b < r.cost);
    });
  }
  rows = out;
}

async function loadData() {
  const seq = ++loadSeq; // overlapping calls: only the newest may render
  const banner = $('errorBanner');
  banner.hidden = true;
  const active = skills.filter((s) => state.skillFilter[s.skill] !== false);
  if (skills.length && !active.length) {
    allRows = [];
    rows = [];
    renderMeta();
    renderTable();
    return;
  }
  try {
    const res = await api(`/api/recipes?${buildQuery()}`);
    if (seq !== loadSeq) return; // a newer request superseded this one
    meta = res.meta;
    allRows = res.rows;
    applyFilters();
    renderMeta();
    renderTable();
  } catch (e) {
    if (seq !== loadSeq) return;
    banner.textContent = String(e.message ?? e);
    banner.hidden = false;
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
    tip: 'GE sell-route profit per craft = gross - GE tax (2%, exempt <50 gp) - cost.' },
  { key: 'ha', label: 'HA', sortable: true,
    tip: 'High Level Alchemy payout per craft = product qty x floor(60% x static value).' },
  { key: 'ha_net', label: 'HA Net', sortable: true,
    tip: 'Alchemy-route profit per craft = HA - min(Craft, Buy x qty) - alchemy cost (Nature rune instant-buy, live).' },
  { key: 'la', label: 'LA', sortable: true,
    tip: 'Low Level Alchemy payout per craft = product qty x floor(40% x static value).' },
  { key: 'la_net', label: 'LA Net', sortable: true,
    tip: 'Alchemy-route profit per craft = LA - min(Craft, Buy x qty) - alchemy cost (Nature rune instant-buy, live).' },
  { key: 'best_net', label: 'Best\nNet', sortable: true,
    tip: 'Best route per craft = max over the enabled routes (Sell Net, HA Net, LA Net).' },
  { key: 'return', label: 'Return', sortable: true,
    tip: 'Return multiple = (Best Net + lowest acquisition) ÷ lowest acquisition (Craft vs Buy x qty). ≥1× = profit.' },
  { key: 'max_crafts_4h', label: '4h count', sortable: true,
    tip: 'Max crafts per 4 hours under Jagex GE buy limits (min over every material and the product). net/4h in the row detail.' },
];

const alch = (r, frac) => (r.product.value == null ? null : Math.floor(r.product.value * frac) * r.product.qty);
const alchNet = (r, frac) => {
  const a = alch(r, frac);
  const fee = meta && meta.alchemy_cost;
  if (a == null || fee == null) return null;
  // product in hand via cheapest route: craft the batch, or buy qty units on GE
  let base = r.cost;
  if (r.product.buy != null && r.product.buy * r.product.qty < base) base = r.product.buy * r.product.qty;
  return a - base - fee;
};
const bestNet = (r) => {
  const cands = [];
  if (routeOn('ge')) cands.push(r.net);
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
const minAcq = (r) => {
  let base = r.cost;
  if (r.product.buy != null && r.product.buy * r.product.qty < base) base = r.product.buy * r.product.qty;
  return base;
};
// Return = (Best Net + lowest acquisition) ÷ lowest acquisition = payout ÷ cost
const returnMul = (r) => {
  const best = bestNet(r);
  if (best == null) return null;
  const base = minAcq(r);
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
      : `alchemy cost (${natureLink}): <span class="gp">${meta.alchemy_cost.toLocaleString()} gp</span>`,
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
const routeOn = (id) => state.routes.includes(id);
const visibleCols = () => COLS.filter((c) => !routeOf.has(c.key) || routeOn(routeOf.get(c.key)));

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
      if (c.key === 'members' || c.key === 'cost') th.classList.add('gsep');
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
    // struck = not the best route this row; best stays clean
    const netCls = (v) => `${v > 0 ? 'pos' : 'neg'}${v < bN ? ' strike' : ''}`;
    // payout struck when its route's net is not the best (matches the net cell)
    const payCls = (netV) => (netV != null && netV < bN ? 'gp strike' : 'gp');
    // struck = the higher of Craft vs Buy (unpicked acquisition); buy x qty = per craft
    const pBuyTotal = r.product.buy != null ? r.product.buy * r.product.qty : null;
    const craftCls = 'gp' + (pBuyTotal != null && pBuyTotal < r.cost ? ' strike' : '');
    const buyCls = 'gp' + (pBuyTotal != null && pBuyTotal > r.cost ? ' strike' : '');
    const cells = [num(r.xp), num(r.cost, craftCls + ' gsep'), numStock(r.product.buy, r.product.buy_vol, buyCls)];
    if (routeOn('ge')) cells.push(numStock(r.gross, r.product.vol, payCls(r.net) + ' gsep'), num(r.net, netCls(r.net)));
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
$('acqFilter').addEventListener('change', (e) => { state.acq = [...e.target.selectedOptions].map((o) => o.value); saveState(); scheduleLoad(); });
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
$('refresh').addEventListener('click', loadData);
$('fetchPlayer').addEventListener('click', fetchPlayer);
$('player').addEventListener('keydown', (e) => { if (e.key === 'Enter') fetchPlayer(); });
$('player').addEventListener('input', (e) => { state.playerName = e.target.value; saveState(); });

// ---------- init ----------

async function init() {
  loadState();
  $('f2pOnly').checked = state.f2pOnly;
  $('profitableOnly').checked = state.profitableOnly;
  for (const opt of $('acqFilter').options) opt.selected = state.acq.includes(opt.value);
  for (const opt of $('routeFilter').options) opt.selected = state.routes.includes(opt.value);
  $('filterLevels').checked = state.filterLevels;
  $('player').value = state.playerName;
  $('search').value = state.search;
  $('searchMaterials').checked = state.searchMaterials;

  try {
    const s = await api('/api/skills');
    skills = s.skills;
    renderLevels();
  } catch (e) {
    $('errorBanner').textContent = `backend unreachable: ${e.message}`;
    $('errorBanner').hidden = false;
  }
  renderHead();
  await loadData();
  // auto-refresh every 30 s; skip while the tab is hidden
  setInterval(() => { if (!document.hidden) loadData(); }, 30000);
  // saved player -> fill fields automatically
  if (state.playerName.trim()) fetchPlayer();
}

init();
