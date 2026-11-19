'use strict';

const LS_KEY = 'osrs_arb_ui_v2';

const state = {
  levels: {},        // skill -> string ("" = no filter)
  skillFilter: {},   // skill -> bool (include in table; default true)
  mode: 'conservative',
  f2pOnly: false,
  profitableOnly: false,
  filterLevels: true,
  minVolume: 0,
  playerName: '',
  search: '',
};

let skills = [];
let modes = ['conservative', 'optimistic'];
let rows = [];
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

function itemLinks(id, name) {
  let html = esc(name);
  if (id !== null && id !== undefined) {
    html += iconLink(PRICES_ITEM_URL + id, PRICES_FAVICON, 'GE prices');
    html += iconLink(WIKI_ITEM_URL + encodeURIComponent(name).replace(/%20/g, '_'), WIKI_FAVICON, 'OSRS Wiki');
  }
  return html;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
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
  wrap.innerHTML = '';
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
  p.set('mode', state.mode);
  if (state.f2pOnly) p.set('f2p_only', 'true');
  if (state.filterLevels) {
    const levels = Object.entries(state.levels)
      .map(([k, v]) => [k, parseInt(v, 10)])
      .filter(([, v]) => Number.isFinite(v) && v > 0)
      .map(([k, v]) => `${k}:${v}`);
    if (levels.length) p.set('levels', levels.join(','));
  }
  if (state.minVolume > 0) p.set('min_volume', String(state.minVolume));
  const q = state.search.trim();
  if (q) p.set('q', q);
  return p.toString();
}

let loadTimer = null;
function scheduleLoad() {
  clearTimeout(loadTimer);
  loadTimer = setTimeout(loadData, 350);
}

async function loadData() {
  const banner = $('errorBanner');
  banner.hidden = true;
  const active = skills.filter((s) => state.skillFilter[s.skill] !== false);
  if (skills.length && !active.length) {
    rows = [];
    renderMeta();
    renderTable();
    return;
  }
  try {
    const res = await api(`/api/recipes?${buildQuery()}`);
    meta = res.meta;
    // best-net filter runs client-side: HA/LA nets need the live alchemy cost
    rows = state.profitableOnly ? res.rows.filter((r) => bestNet(r) > 0) : res.rows;
    renderMeta();
    renderTable();
  } catch (e) {
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
    tip: 'Skill level required for this recipe.' },
  { key: 'xp', label: 'XP', sortable: true,
    tip: 'Experience gained per craft, from the OSRS wiki (0 = service actions like tanning, or the (unf) step of a potion).' },
  { key: 'cost', label: 'Craft', sortable: true,
    tip: 'Cheapest acquisition cost per craft = for each material the cheaper of buying or crafting it, x qty, plus fees (e.g. tanning).' },
  { key: 'buy', label: 'Buy', sortable: true,
    tip: 'Grand Exchange buy price of the product, per unit.' },
  { key: 'gross', label: 'Sell', sortable: true,
    tip: 'Grand Exchange sell revenue per craft = GE sell price x product qty.' },
  { key: 'net', label: 'Sell Net', sortable: true,
    tip: 'GE sell-route profit per craft = gross - GE tax (2%, exempt <=100 gp) - cost.' },
  { key: 'ha', label: 'HA', sortable: true,
    tip: 'High Level Alchemy payout = floor(60% x static value).' },
  { key: 'ha_net', label: 'HA Net', sortable: true,
    tip: 'Alchemy-route profit per craft = HA - min(Craft, Buy) - alchemy cost (Nature rune instant-buy, live).' },
  { key: 'la', label: 'LA', sortable: true,
    tip: 'Low Level Alchemy payout = floor(40% x static value).' },
  { key: 'la_net', label: 'LA Net', sortable: true,
    tip: 'Alchemy-route profit per craft = LA - min(Craft, Buy) - alchemy cost (Nature rune instant-buy, live).' },
  { key: 'best_net', label: 'Best Net', sortable: true,
    tip: 'Best route per craft = max(Sell Net, HA Net, LA Net).' },
  { key: 'volume', label: 'Vol/5m', sortable: true,
    tip: '5-minute trade volume of the scarcest item: product sell volume vs each material buy volume / qty. Low = profit you cannot actually move.' },
  { key: 'max_crafts_4h', label: '4h count', sortable: true,
    tip: 'Max crafts per 4 hours under Jagex GE buy limits (min over every material and the product). net/4h in the row detail.' },
];

const alch = (r, frac) => (r.product.value == null ? null : Math.floor(r.product.value * frac));
const alchNet = (r, frac) => {
  const a = alch(r, frac);
  const fee = meta && meta.alchemy_cost;
  if (a == null || fee == null) return null;
  // product in hand via cheapest route: craft it, or buy it on GE
  let base = r.cost;
  if (r.product.buy != null && r.product.buy < base) base = r.product.buy;
  return a - base - fee;
};
const bestNet = (r) => {
  const cands = [r.net];
  const h = alchNet(r, 0.6), l = alchNet(r, 0.4);
  if (h != null) cands.push(h);
  if (l != null) cands.push(l);
  return Math.max(...cands);
};

function cellValue(r, key) {
  if (key === 'product') return r.product.name;
  if (key === 'buy') return r.product.buy;
  if (key === 'ha') return alch(r, 0.6);
  if (key === 'la') return alch(r, 0.4);
  if (key === 'ha_net') return alchNet(r, 0.6);
  if (key === 'la_net') return alchNet(r, 0.4);
  if (key === 'best_net') return bestNet(r);
  return r[key];
}

function renderMeta() {
  if (!meta) return;
  const bits = [
    meta.alchemy_cost == null
      ? 'alchemy cost (Nature rune): —'
      : `alchemy cost (Nature rune): ${meta.alchemy_cost.toLocaleString()} gp`,
    'prices updated ' + (meta.last_refresh ? new Date(meta.last_refresh * 1000).toLocaleTimeString() : '—'),
  ];
  $('meta').textContent = bits.join(' · ');

  const best = rows.length ? Math.max(...rows.map((r) => bestNet(r))) : 0;
  $('status').textContent = rows.length
    ? `${rows.length} recipes · best net ${best.toLocaleString()} gp/craft`
    : 'No rows — adjust filters or wait for the first price refresh.';
}

function renderHead() {
  const tr = document.createElement('tr');
  for (const c of COLS) {
    const th = document.createElement('th');
    th.textContent = c.label;
    if (c.tip) th.title = c.tip;
    if (c.sortable) {
      th.className = 'sortable';
      th.dataset.key = c.key;
      if (sortKey === c.key) th.textContent += sortDir === 'asc' ? ' ▲' : ' ▼';
    }
    tr.append(th);
  }
  $('thead').replaceChildren(tr);
}

function detailHtml(r) {
  const sect = (label) => `<tr class="sect"><td colspan="9">${label}</td></tr>`;
  const val = (v, strike) => (v === null || v === undefined ? '<span class="dim">—</span>' : `<span class="gp${strike ? ' strike' : ''}">${fmt(v)}</span>`);
  const row = (name, craftEach, buyEach, craftTotal, buyTotal, sellEach, sellTotal, tax, stock = null) => {
    const hasCraft = craftEach !== null && craftEach !== undefined;
    const craftHigher = hasCraft && buyEach !== null && buyEach !== undefined && craftEach > buyEach;
    return `<tr><td>${name}</td>` +
      `<td>${val(craftEach, craftHigher)}</td>` +
      `<td>${val(craftTotal, craftHigher)}</td>` +
      `<td>${val(buyEach, hasCraft && !craftHigher)}</td>` +
      `<td>${val(buyTotal, hasCraft && !craftHigher)}</td>` +
      `<td>${val(sellEach)}</td><td>${val(sellTotal)}</td><td>${val(tax)}</td><td>${val(stock)}</td></tr>`;
  };
  const lines = [];

  lines.push('<table class="detail-table"><thead><tr><th>Name</th><th>Craft each</th><th>Craft total</th><th>Buy each</th><th>Buy total</th><th>Sell each</th><th>Sell total</th><th>Tax</th>' +
    '<th title="Grand Exchange stock at that price: units traded at that price point in the 5m (or 1h) window. 0 = no trades at that price in the window.">Stock @ price</th></tr></thead><tbody>');

  if (r.tools && r.tools.length) {
    lines.push(sect('Tools'));
    for (const t of r.tools) {
      const name = t.id !== null && t.id !== undefined ? itemLinks(t.id, t.name) : esc(t.name);
      lines.push(row(name, null, t.buy, null, t.buy, null, null, null));
    }
  }
  if (r.facilities && r.facilities.length) {
    lines.push(sect('Facilities'));
    for (const f of r.facilities) lines.push(row(esc(f), null, null, null, null, null, null, null));
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
    const name = `${m.qty > 1 ? m.qty + '× ' : ''}${itemLinks(m.id, m.name)}`;
    lines.push(row(name, m.craft, m.price, hasCraft ? m.craft * m.qty : null, m.price * m.qty, null, null, null, m.vol ?? null));
  }
  if (r.materials.length > 1) {
    lines.push(row('<b>Materials total</b>', null, null, matsCraftTotal || null, matsBuyTotal || null, null, null, null));
  }
  lines.push(sect('Product'));
  const prodName = `${r.product.qty > 1 ? r.product.qty + '× ' : ''}${itemLinks(r.product.id, r.product.name)}`;
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
    td.colSpan = COLS.length;
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
    b.innerHTML = itemLinks(r.product.id, r.product.name);
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
        const mark = crafted ? ' <span class="crafted" title="cheaper to craft than to buy">⚒</span>' : '';
        return `${m.qty > 1 ? m.qty + '× ' : ''}${itemLinks(m.id, m.name)}<small> (${fmt(eff)}${mark})</small>`;
      })
      .join(', ') + (r.fee > 0 ? `<small> +${fmt(r.fee)} fee</small>` : '');
    tdM.title = r.materials
      .map((m) => {
        const { eff, crafted } = matDesc(m);
        return `${m.qty}x ${m.name} @ ${fmt(eff)} gp${crafted ? ' (crafted, cheaper than buying)' : ''}`;
      }).join(', ');
    tr.append(tdM);

    // members star
    const tdB = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = 'badge ' + (r.members ? 'members' : 'f2p');
    badge.textContent = '★';
    badge.title = r.members ? 'Members' : 'Free-to-play';
    tdB.append(badge);
    tr.append(tdB);

    // skill required + level needed
    const tdS = document.createElement('td');
    tdS.textContent = r.skill;
    tr.append(tdS);

    const num = (v, cls) => {
      const td = document.createElement('td');
      if (cls) td.className = cls;
      td.textContent = fmt(v);
      return td;
    };
    const haN = alchNet(r, 0.6);
    const laN = alchNet(r, 0.4);
    const bN = bestNet(r);
    // struck = not the best route this row; best stays clean
    const netCls = (v) => `${v > 0 ? 'pos' : 'neg'}${v < bN ? ' strike' : ''}`;
    // struck = the higher of Craft vs Buy (unpicked acquisition)
    const pBuy = r.product.buy;
    const craftCls = 'gp' + (pBuy != null && pBuy < r.cost ? ' strike' : '');
    const buyCls = 'gp' + (pBuy != null && pBuy > r.cost ? ' strike' : '');
    tr.append(num(r.level), num(r.xp), num(r.cost, craftCls), num(pBuy, buyCls), num(r.gross, 'gp'),
      num(r.net, netCls(r.net)),
      num(alch(r, 0.6), 'gp'),
      num(haN, haN == null ? null : netCls(haN)),
      num(alch(r, 0.4), 'gp'),
      num(laN, laN == null ? null : netCls(laN)),
      num(bN, netCls(bN)));
    tr.append(num(r.volume), num(r.max_crafts_4h));
    tbody.append(tr);

    if (expanded.has(r.recipe_id)) {
      const dtr = document.createElement('tr');
      dtr.className = 'detail-row';
      const td = document.createElement('td');
      td.colSpan = COLS.length;
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

$('mode').addEventListener('change', (e) => { state.mode = e.target.value; saveState(); scheduleLoad(); });
$('f2pOnly').addEventListener('change', (e) => { state.f2pOnly = e.target.checked; saveState(); scheduleLoad(); });
$('profitableOnly').addEventListener('change', (e) => { state.profitableOnly = e.target.checked; saveState(); scheduleLoad(); });
$('filterLevels').addEventListener('change', (e) => { state.filterLevels = e.target.checked; saveState(); scheduleLoad(); });
$('minVolume').addEventListener('input', (e) => {
  state.minVolume = Math.max(0, parseInt(e.target.value, 10) || 0);
  saveState();
  scheduleLoad();
});
$('search').addEventListener('input', (e) => { state.search = e.target.value; saveState(); scheduleLoad(); });
$('refresh').addEventListener('click', loadData);
$('fetchPlayer').addEventListener('click', fetchPlayer);
$('player').addEventListener('keydown', (e) => { if (e.key === 'Enter') fetchPlayer(); });
$('player').addEventListener('input', (e) => { state.playerName = e.target.value; saveState(); });

// ---------- init ----------

async function init() {
  loadState();
  $('mode').value = state.mode;
  $('f2pOnly').checked = state.f2pOnly;
  $('profitableOnly').checked = state.profitableOnly;
  $('filterLevels').checked = state.filterLevels;
  $('minVolume').value = state.minVolume;
  $('player').value = state.playerName;
  $('search').value = state.search;

  try {
    const [s, m] = await Promise.all([api('/api/skills'), api('/api/meta')]);
    skills = s.skills;
    modes = m.mode_options;
    const sel = $('mode');
    sel.replaceChildren(...modes.map((mode) => {
      const o = document.createElement('option');
      o.value = mode;
      o.textContent = mode;
      return o;
    }));
    sel.value = state.mode;
    renderLevels();
  } catch (e) {
    $('errorBanner').textContent = `backend unreachable: ${e.message}`;
    $('errorBanner').hidden = false;
  }
  renderHead();
  await loadData();
  setInterval(loadData, 30000);
  // saved player -> fill fields automatically
  if (state.playerName.trim()) fetchPlayer();
}

init();
