// FinReflectKG Time-Travel demo — frontend (DVR timeline). Talks to the FastAPI backend (demo/api.py).
// The whole decade for a company comes down in ONE /api/timeline payload; the union of all years is
// laid out once with stable positions, so scrubbing the slider is a pure crossfade (no fetch, no
// relayout) — DVR-smooth. Legend clicks, the valid/reported axis, and the Top-N PageRank slider are
// all visibility filters on top of that.
const TYPE_COLORS = {
  FIN_METRIC: '#5b8def', FIN_INST: '#7c6cf0', ORG: '#e0a34a', COMP: '#c9902f',
  GPE: '#4ec98a', PRODUCT: '#e46a6a', RISK_FACTOR: '#d9534f', SEGMENT: '#4bb7c9',
  PERSON: '#c86fd0', FIN_MARKET: '#3fa7ff', SUPPLIER: '#b9772e', CUSTOMER: '#a76fd0',
  EVENT: '#e8b04b', SECTOR: '#38b2ac', MACRO_CONDITION: '#8a97ad', ORG_REG: '#d94fb0',
  LOGISTICS: '#6fa8dc', ECON_IND: '#66c2a5', LITIGATION: '#e07a5f',
};
const LEGEND_TYPES = ['FIN_METRIC', 'FIN_INST', 'ORG', 'GPE', 'PRODUCT', 'RISK_FACTOR', 'SEGMENT', 'PERSON', 'FIN_MARKET'];
const colorFor = (t) => TYPE_COLORS[t] || '#8a97ad';
const $ = (s) => document.querySelector(s);
// Container Manager serves this UI under /_service/uds/_db/<db>/<app>/ (or
// /_global/<app>/). Absolute `/api/...` and `/style.css` would miss that prefix
// and hit the coordinator root. Resolve against the page's directory instead.
const serviceBase = (() => {
  const p = location.pathname;
  if (p.endsWith('/')) return p;
  const leaf = p.slice(p.lastIndexOf('/') + 1);
  if (leaf.includes('.')) return p.slice(0, p.lastIndexOf('/') + 1);
  return p + '/';
})();
const j = (u) => fetch(serviceBase + u.replace(/^\//, ''), { credentials: 'same-origin' })
  .then((r) => {
    if (!r.ok) throw new Error(`${u} failed: ${r.status}`);
    return r.json();
  });
const edgeKey = (e) => `${e.source}~${e.label}~${e.target}`;

let cy, ticker = 'aapl', year = 2018, clean = true, depth = 1, axis = 'valid';
let timeline = null;                 // { focal, years: { Y: {nodeIds:Set, edgeIds:Set, total} } }
let focalId = null;
let hidden = new Set();              // node types switched off via the legend
let prTopN = 0;                      // 0 = off; otherwise show only the top-N PageRank entities
let prSet = null;                    // Set of node ids allowed by the PR filter (or null = off)
let prOrder = {};                    // anchor year -> [node ids ranked by PageRank]
let anchors = [2014, 2019, 2020, 2024];
const infCache = {}, diffCache = {};

// Cytoscape bakes its stylesheet at init, so the graph's own colours have to be
// read out of the CSS custom properties rather than hardcoded — otherwise the
// canvas stays dark-themed while the chrome switches. graphStyle() is rebuilt and
// re-applied on every theme change (see applyTheme below).
const cssVar = (name, fallback) => {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
};

function graphStyle() {
  const label = cssVar('--graph-label', '#cfd8e6');
  const edge = cssVar('--graph-edge', '#31405c');
  const edgeLabel = cssVar('--graph-edge-label', '#576a82');
  const accent = cssVar('--accent', '#5b8def');
  const green = cssVar('--green', '#2fa86b');
  const red = cssVar('--red', '#e46a6a');
  return [
    { selector: 'node', style: {
      'background-color': 'data(color)', 'label': 'data(label)', 'color': label,
      'font-size': '9px', 'text-wrap': 'wrap', 'text-max-width': '84px',
      // Floor raised 14 -> 17: a degree-1 leaf was small enough to disappear under
      // an arrowhead or a neighbour's label.
      'width': 'mapData(deg,1,25,17,46)', 'height': 'mapData(deg,1,25,17,46)',
      'text-valign': 'bottom', 'text-margin-y': '3px', 'min-zoomed-font-size': 6,
      // Surface-coloured ring + explicit z-index so every node reads as a distinct
      // mark above its own edge, the arrowhead, and any label behind it.
      'border-width': 1.5, 'border-color': cssVar('--graph-node-ring', '#0f172a'),
      'border-opacity': 1, 'z-index': 10,
      'transition-property': 'opacity, background-color, width, height', 'transition-duration': '260ms' } },
    { selector: 'node.company', style: {
      'background-color': cssVar('--graph-company-fill', '#ffffff'),
      'border-color': accent, 'border-width': 4,
      'font-size': '15px', 'color': cssVar('--graph-company-label', '#ffffff'), 'font-weight': 'bold',
      'width': 56, 'height': 56, 'z-index': 30, 'min-zoomed-font-size': 0 } },
    { selector: 'node.bnode', style: {
      'border-color': green, 'border-width': 2, 'border-style': 'dashed', 'shape': 'round-rectangle' } },
    { selector: 'node.junk', style: {
      'background-color': red, 'border-color': red, 'shape': 'diamond', 'opacity': 0.9 } },
    { selector: 'edge', style: {
      'width': 1, 'line-color': edge, 'target-arrow-color': edge,
      // arrow-scale down from 0.7: the arrowhead was competing with the small
      // target node for attention. z-index keeps edges under the node marks.
      'target-arrow-shape': 'triangle', 'arrow-scale': 0.55, 'curve-style': 'bezier',
      'label': 'data(label)', 'font-size': '7px', 'color': edgeLabel,
      'text-rotation': 'autorotate', 'opacity': 0.75, 'min-zoomed-font-size': 7,
      'z-index': 1,
      'transition-property': 'opacity, line-color', 'transition-duration': '260ms' } },
    // MUST BE LAST. Cytoscape resolves same-property conflicts by rule order, so a
    // `.off` rule placed before `edge` loses its opacity:0 to the edge base opacity —
    // which left hidden nodes' edges still painting, i.e. arrows into empty space.
    { selector: '.off', style: {
      'opacity': 0, 'events': 'no', 'text-opacity': 0,
      // Belt-and-braces: zero the arrow explicitly so no later default can revive it.
      'target-arrow-color': 'transparent', 'line-color': 'transparent' } },
  ];
}

function initCy() {
  cy = cytoscape({ container: $('#cy'), wheelSensitivity: 0.3, style: graphStyle() });
}

// ── Theme (light default + dark toggle; mirrors the r2g Studio control) ──
function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}
function applyTheme(theme) {
  const t = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem('finreflectkg.theme', t); } catch (e) { /* ignore */ }
  const btn = document.getElementById('btn-theme');
  if (btn) {
    // Show the icon for the mode you'd switch TO.
    btn.innerHTML = t === 'dark' ? '&#9728;' : '&#9790;'; // ☀ when dark, ☾ when light
    btn.setAttribute('aria-label', t === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
  }
  // Re-read the tokens and repaint the canvas; keeps the graph in step with the chrome.
  if (cy) cy.style().fromJson(graphStyle()).update();
}
function toggleTheme() { applyTheme(currentTheme() === 'dark' ? 'light' : 'dark'); }

const nearestAnchor = (y) => anchors.reduce((a, b) => (Math.abs(b - y) < Math.abs(a - y) ? b : a), anchors[0]);

async function rebuild() {
  $('#meta').textContent = 'building timeline…';
  const d = await j(`api/timeline?ticker=${ticker}&depth=${depth}&clean=${clean}&axis=${axis}&limit=140`);
  focalId = d.focal;
  const unionN = new Map(), unionE = new Map(), years = {};
  for (const [Y, yd] of Object.entries(d.years)) {
    const nset = new Set(), eset = new Set();
    yd.nodes.forEach((n) => { unionN.set(n.id, n); nset.add(n.id); });
    yd.edges.forEach((e) => { const k = edgeKey(e); unionE.set(k, e); eset.add(k); });
    years[Y] = { nodeIds: nset, edgeIds: eset, total: yd.total };
  }
  timeline = { focal: d.focal, years };
  if (!focalId || unionN.size === 0) { cy.elements().remove(); $('#meta').textContent = `no facts for ${ticker}`; return; }

  const deg = {};
  unionE.forEach((e) => { deg[e.source] = (deg[e.source] || 0) + 1; deg[e.target] = (deg[e.target] || 0) + 1; });

  cy.elements().remove();
  const els = [];
  unionN.forEach((n) => {
    const cls = ['off'];   // born hidden; renderYear reveals the current year
    if (n.id === focalId && !n.bnode) cls.push('company');
    if (n.bnode) cls.push('bnode');
    if (n.junk) cls.push('junk');
    els.push({ group: 'nodes', data: { id: n.id, label: n.label, type: n.type, color: colorFor(n.type), deg: deg[n.id] || 1 }, classes: cls.join(' ') });
  });
  unionE.forEach((e) => els.push({ group: 'edges', data: { id: edgeKey(e), source: e.source, target: e.target, label: e.label }, classes: 'off' }));
  cy.add(els);

  const focal = cy.getElementById(focalId);
  if (focal.nonempty()) focal.unlock();
  const N = cy.nodes().length;
  cy.layout({
    name: 'cose', animate: true, animationDuration: 600, randomize: true, fit: false,
    nodeRepulsion: 20000, idealEdgeLength: 95, edgeElasticity: 120, gravity: 0.35,
    numIter: N > 450 ? 700 : 1200, nodeOverlap: 26, componentSpacing: 140, coolingFactor: 0.96, padding: 40,
  }).one('layoutstop', () => {
    if (focal.nonempty()) focal.lock();
    updatePrSet();
    renderYear();
    cy.fit(cy.nodes().not('.off'), 55);
    if (focal.nonempty()) cy.center(focal);
  }).run();
}

function updatePrSet() {
  if (!prTopN) { prSet = null; return; }
  const order = prOrder[nearestAnchor(year)] || [];
  prSet = new Set(order.slice(0, prTopN));
  if (focalId) prSet.add(focalId);       // the company itself always stays
}

// Pure client-side crossfade to the given year — no network, no relayout.
function renderYear() {
  if (!timeline) return;
  const ys = timeline.years[String(year)];
  if (!ys) return;
  cy.batch(() => {
    cy.nodes().forEach((n) => {
      const id = n.id();
      const on = ys.nodeIds.has(id) && !hidden.has(n.data('type')) && (!prSet || prSet.has(id));
      n.toggleClass('off', !on);
    });
    cy.edges().forEach((e) => {
      const on = ys.edgeIds.has(e.id()) && !e.source().hasClass('off') && !e.target().hasClass('off');
      e.toggleClass('off', !on);
    });
  });
  const shown = cy.edges().not('.off').length;
  // Diagnostic — an arrow into empty space has two possible causes and the first
  // version of this check only caught one of them, so it read 0 while the bug was live.
  //   modelOrphans:  an edge we intend to show whose endpoint is hidden/absent.
  //   paintLeaks:    an edge we intend to HIDE that is still being painted, because a
  //                  later stylesheet rule overrode `.off`'s opacity. This is the one
  //                  that actually bit us, and it is only visible in the resolved style.
  let modelOrphans = 0, paintLeaks = 0;
  cy.edges().forEach((e) => {
    const s = e.source(), t = e.target();
    const endpointGone = s.empty() || t.empty() || s.hasClass('off') || t.hasClass('off');
    if (!e.hasClass('off')) { if (endpointGone) modelOrphans++; }
    else if (parseFloat(e.style('opacity')) > 0) paintLeaks++;
  });
  const orphanEdges = modelOrphans + paintLeaks;
  // How many visible edges are genuine multi-hop (neither endpoint is the company)?
  // That is the whole point of depth >= 2, so show it rather than leaving the user to
  // squint at a star and wonder whether the Depth control did anything.
  let ctxEdges = 0;
  if (depth > 1) {
    cy.edges().not('.off').forEach((e) => {
      if (e.source().id() !== focalId && e.target().id() !== focalId) ctxEdges++;
    });
  }
  // The PageRank filter ranks GLOBALLY, so "top 200" keeps only the handful of
  // corpus-wide leaders that happen to sit in this company's neighbourhood. Show that
  // survivor count, or the label reads as a promise of 200 nodes it never made.
  const prkept = $('#prkept');
  if (prkept) {
    const vis = cy.nodes().not('.off').length;
    prkept.textContent = prSet ? ` — ${vis} of ${ys.nodeIds.size} here` : '';
  }
  const axisLbl = axis === 'valid' ? 'as of' : 'as reported';
  $('#meta').textContent = `${shown} of ${ys.total.toLocaleString()} facts · depth ${depth}`
    + (depth > 1 ? ` (${ctxEdges} context)` : '') + ` · ${axisLbl} ${year}`
    + (clean ? '' : ' · RAW')
    + (orphanEdges ? ` · ⚠ ${modelOrphans} orphan / ${paintLeaks} leaked` : '');
  window.__frkg = { focal: focalId, year, axis, depth, visNodes: cy.nodes().not('.off').length,
                    visEdges: shown, ctxEdges, modelOrphans, paintLeaks, orphanEdges, prTopN };
}

async function loadInfluence() {
  const anchor = nearestAnchor(year);
  $('#infhdr').textContent = `PageRank · ${anchor}`;
  if (!infCache[anchor]) infCache[anchor] = await j(`api/influence?year=${anchor}&top=15`);
  $('#influence').innerHTML = infCache[anchor].rows
    .map((r) => `<li>${r.name} <span class="t">${r.type}</span></li>`).join('');
}

async function loadDiff() {
  const base = 2014;
  $('#diffhdr').textContent = `${year} vs ${base}`;
  if (year === base) { $('#appeared').innerHTML = '<li class="empty">pick another year</li>'; $('#disappeared').innerHTML = ''; return; }
  const key = `${ticker}|${year}`;
  if (!diffCache[key]) diffCache[key] = await j(`api/diff?ticker=${ticker}&from=${base}&to=${year}&limit=25`);
  const d = diffCache[key];
  const fmt = (xs) => xs.length
    ? xs.map((x) => `<li title="${x.from} —${x.rel}→ ${x.to}">${x.to}</li>`).join('')
    : '<li class="empty">none</li>';
  $('#appeared').innerHTML = fmt(d.appeared);
  $('#disappeared').innerHTML = fmt(d.disappeared);
}

async function loadBackward() {
  const d = await j(`api/backward?ticker=${ticker}&lag=3&limit=20`);
  $('#backward').innerHTML = d.length
    ? d.map((x) => `<li><span class="yr">filed ${x.filed} → ${x.period}</span> <b>${x.to}</b> <span class="t">(${x.rel})</span></li>`).join('')
    : '<li class="empty">none</li>';
}

async function ensurePrOrder() {   // prefetch PageRank rankings for each anchor (for the Top-N filter)
  await Promise.all(anchors.map(async (a) => {
    if (!prOrder[a]) prOrder[a] = (await j(`api/prranks?year=${a}&top=300`)).ids;
  }));
}

// ---- side panels (debounced so slider scrubbing stays smooth) ----
let sideT;
function scheduleSide() { clearTimeout(sideT); sideT = setTimeout(() => { loadInfluence(); loadDiff(); }, 140); }
let rafPending = false;
function scheduleRender() { if (rafPending) return; rafPending = true; requestAnimationFrame(() => { rafPending = false; updatePrSet(); renderYear(); }); }

function onSlider(v) { year = +v; $('#yearlbl').textContent = year; scheduleRender(); scheduleSide(); }

async function refreshTicker() { infCacheClear(); await rebuild(); loadInfluence(); loadDiff(); loadBackward(); }
function infCacheClear() { for (const k in diffCache) delete diffCache[k]; }

(async function () {
  initCy();
  // The pre-paint script in index.html already set data-theme; sync the button
  // glyph and the canvas to whatever it resolved to.
  applyTheme(currentTheme());
  const yrs = await j('api/years');
  anchors = yrs.anchors || anchors;
  const yr = $('#year'); yr.min = yrs.min; yr.max = yrs.max;
  const tks = await j('api/tickers');
  $('#tickers').innerHTML = tks.map((t) => `<option value="${t}">`).join('');
  $('#legend').innerHTML = '<span class="lbl">filter:</span>' + LEGEND_TYPES
    .map((t) => `<span data-type="${t}" title="click to show / hide ${t}"><i style="background:${colorFor(t)}"></i>${t}</span>`).join('');
  $('#legend').querySelectorAll('span[data-type]').forEach((el) => {
    el.addEventListener('click', () => {
      const t = el.dataset.type;
      if (hidden.has(t)) { hidden.delete(t); el.classList.remove('legoff'); }
      else { hidden.add(t); el.classList.add('legoff'); }
      renderYear();
    });
  });
  $('#ticker').value = ticker;

  yr.addEventListener('input', (e) => onSlider(e.target.value));
  $('#ticker').addEventListener('change', (e) => { const v = e.target.value.trim().toLowerCase(); if (v) { ticker = v; refreshTicker(); } });
  $('#depth').addEventListener('change', (e) => { depth = +e.target.value; rebuild(); });
  $('#axis').addEventListener('change', (e) => { axis = e.target.value; rebuild(); });
  $('#clean').addEventListener('change', (e) => { clean = e.target.checked; rebuild(); });
  $('#pr').addEventListener('input', (e) => {
    prTopN = +e.target.value;
    $('#prlbl').textContent = prTopN ? `global PageRank top ${prTopN}` : 'all entities';
    scheduleRender();
  });

  await rebuild();
  loadInfluence(); loadDiff(); loadBackward();
  ensurePrOrder();   // background: warm the PageRank rankings so the Top-N slider is instant
})();
