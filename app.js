/* Mapa Eleições 2026 — 1º turno. Dados: TSE (resultados e dados abertos), malhas: IBGE. */
(() => {
'use strict';

// ------------------------------------------------------------------ utilidades
const $ = s => document.querySelector(s);
const fmtInt = new Intl.NumberFormat('pt-BR');
const fmtPct = (x, d = 2) => (x * 100).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }) + '%';
const fmtPP = (x, d = 1) => (x >= 0 ? '+' : '−') + Math.abs(x * 100).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtCompact = x => x >= 1e6 ? (x / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi'
  : x >= 1e3 ? (x / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mil' : fmtInt.format(Math.round(x));
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const titleCase = s => s.toLowerCase().replace(/(^|[\s(/-])(\p{L})/gu, (m, a, b) => a + b.toUpperCase())
  .replace(/\b(Da|De|Do|Das|Dos|E)\b/g, w => w.toLowerCase());
const fetchJSON = url => fetch(url).then(r => { if (!r.ok) throw new Error(url + ' ' + r.status); return r.json(); });

function quantile(sorted, p) {
  if (!sorted.length) return 0;
  const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}
// arredonda para um número "bonito" para cima (limites de legenda)
function niceUp(x) {
  if (x <= 0) return x;
  const e = Math.pow(10, Math.floor(Math.log10(x)));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * e >= x) return m * e;
  return 10 * e;
}

// ------------------------------------------------------------------ partidos
const PARTY_COLORS = {
  PT: '#d7263d', PL: '#2453c4', 'UNIÃO': '#22b5e6', PSD: '#f5a524', MDB: '#2fa35b', PP: '#7b61d1',
  REPUBLICANOS: '#16b39a', PSB: '#ff7a1a', PSDB: '#5b8fd9', PDT: '#e2558f', NOVO: '#ff9d4d', PSOL: '#b23aa8',
  PODE: '#42c46b', AVANTE: '#9d5cc9', SOLIDARIEDADE: '#f2c230', 'PC do B': '#9e1b28', PCdoB: '#9e1b28', PV: '#7cc242',
  REDE: '#2bb3a6', CIDADANIA: '#e85d75', PRD: '#8a94a6', AGIR: '#c08b5c', MOBILIZA: '#a3a35c', DC: '#5c7fa3',
  PRTB: '#4e8a5f', PMB: '#d48ac7', PCO: '#a63d3d', PSTU: '#c44', UP: '#b85454', PCB: '#8f2a2a', 'MISSÃO': '#c9a227',
  DEMOCRATA: '#3f6fb5', PMN: '#6fa36f',
};
function partyColor(p) {
  if (PARTY_COLORS[p]) return PARTY_COLORS[p];
  let h = 0; for (const c of p) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return d3.hsl(h % 360, 0.55, 0.55).formatHex();
}

const STATUS = { E: 'Eleito', 2: '2º turno', N: 'Não eleito', S: 'Suplente', A: 'Anulado' };
const STATUS_ORDER = ['E', '2', 'N', 'S', 'A'];
const CARGOS = [
  { id: 1, nome: 'Presidente' }, { id: 3, nome: 'Governador' }, { id: 5, nome: 'Senador' },
  { id: 6, nome: 'Dep. Federal' }, { id: 7, nome: 'Dep. Estadual' },
];

// ------------------------------------------------------------------ métricas
// get(e) recebe {t26,t22,p26,p22,g} e retorna número (ou null)
const share = p => (p && p[0] + p[1] > 0) ? p[0] / (p[0] + p[1]) : null;
const METRICS = [
  { id: 'val', group: 'Participação', name: 'Votos válidos', kind: 'abs',
    get: e => e.t26 ? e.t26[2] : null, icon: 'check' },
  { id: 'pval', group: 'Participação', name: '% votos válidos (sobre o eleitorado)', kind: 'pct',
    get: e => e.t26 && e.t26[0] ? e.t26[2] / e.t26[0] : null, icon: 'checkpct' },
  { id: 'vot', group: 'Participação', name: 'Votos (comparecimento)', kind: 'abs',
    get: e => e.t26 ? e.t26[1] : null, icon: 'urn' },
  { id: 'pvot', group: 'Participação', name: '% votos (comparecimento)', kind: 'pct',
    get: e => e.t26 && e.t26[0] ? e.t26[1] / e.t26[0] : null, icon: 'urnpct' },
  { id: 'dval', group: 'Variação desde 2022', name: 'Δ Votos válidos vs 2022', kind: 'rel', diff: true,
    get: e => e.t26 && e.t22 && e.t22[2] ? e.t26[2] / e.t22[2] - 1 : null, icon: 'check' },
  { id: 'dpval', group: 'Variação desde 2022', name: 'Δ % votos válidos vs 2022', kind: 'pp', diff: true,
    get: e => e.t26 && e.t22 && e.t26[0] && e.t22[0] ? e.t26[2] / e.t26[0] - e.t22[2] / e.t22[0] : null, icon: 'checkpct' },
  { id: 'dvot', group: 'Variação desde 2022', name: 'Δ Votos vs 2022', kind: 'rel', diff: true,
    get: e => e.t26 && e.t22 && e.t22[1] ? e.t26[1] / e.t22[1] - 1 : null, icon: 'urn' },
  { id: 'dpvot', group: 'Variação desde 2022', name: 'Δ % votos vs 2022', kind: 'pp', diff: true,
    get: e => e.t26 && e.t22 && e.t26[0] && e.t22[0] ? e.t26[1] / e.t26[0] - e.t22[1] / e.t22[0] : null, icon: 'urnpct' },
  { id: 'pres', group: 'Presidente', name: 'Presidente: PT × PL', kind: 'pres',
    get: e => share(e.p26), icon: 'pres' },
  { id: 'dpres', group: 'Presidente', name: 'Presidente: variação PT × PL desde 2022', kind: 'dpres', diff: true,
    get: e => { const a = share(e.p26), b = share(e.p22); return a == null || b == null ? null : a - b; }, icon: 'pres' },
  { id: 'gov', group: 'Governador', name: 'Governador: partido mais votado', kind: 'gov',
    get: e => e.g ? e.g[1] : null, icon: 'gov' },
];
const METRIC = Object.fromEntries(METRICS.map(m => [m.id, m]));

const ICONS = {
  check: '<path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
  checkpct: '<path d="M3 11l3.4 3.4L13 7.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="15.5" cy="14.5" r="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="20.5" cy="20" r="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M21 13.5l-6 7" stroke="currentColor" stroke-width="1.4"/>',
  urn: '<rect x="4" y="10" width="16" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 10V4h8v6M10 7h4" fill="none" stroke="currentColor" stroke-width="1.8"/>',
  urnpct: '<rect x="2.5" y="11" width="12" height="9" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M5.5 11V6h6v5" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="17" cy="5.5" r="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="21" cy="11" r="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M21.6 4.5l-5.2 7.6" stroke="currentColor" stroke-width="1.4"/>',
  pres: '<path d="M12 3a9 9 0 0 1 0 18z" fill="#d7263d"/><path d="M12 3a9 9 0 0 0 0 18z" fill="#2453c4"/>',
  gov: '<path d="M4 20h16M6 20v-8M10 20v-8M14 20v-8M18 20v-8M3 10l9-6 9 6z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
};

// ------------------------------------------------------------------ estado
const state = {
  level: 'estado',
  metric: 'pres',
  selected: null,      // id do elemento selecionado
  hover: null,
  transform: d3.zoomIdentity,
};
let S = null;          // summary.json
let geo = {};          // features
const cand = {};       // escopo -> dicionário de candidatos
const detailCache = new Map();
let locais = null;     // pontos do nível Seção (um por local de votação)
let extCities = null;  // nível Seção: locais do exterior como pontos no mapa (id "x<n>")
let worldBase = null;  // nível Seção: países do mundo ao fundo { land, borders } em Path2D

// ------------------------------------------------------------------ canvas
const canvas = $('#map');
const ctx = canvas.getContext('2d');
// (cria o canvas se o HTML em cache for de uma versão anterior)
const overlay = $('#overlay') || $('#map').insertAdjacentElement('afterend', Object.assign(document.createElement('canvas'), { id: 'overlay' }));            // destaques (hover/seleção), redesenhados sem refazer o mapa
const octx = overlay.getContext('2d');
const snap = document.createElement('canvas');   // cópia do último desenho completo, usada durante o zoom
const snapCtx = snap.getContext('2d');
let snapT = null, lastDrawMs = 0;
const hitCtx = document.createElement('canvas').getContext('2d');
let W = 0, H = 0, DPR = 1;
let projection, baseScale;

function resize() {
  DPR = window.devicePixelRatio || 1;
  W = window.innerWidth; H = window.innerHeight;
  for (const c of [canvas, overlay, snap]) { c.width = W * DPR; c.height = H * DPR; }
  draw();
}

// d3-geo é esférico: um anel no sentido anti-horário vira "o globo menos o polígono".
// Inverte qualquer polígono com área maior que meio globo.
function rewind(f) {
  const g = f.geometry;
  if (!g) return;
  const polys = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
  for (const rings of polys) {
    if (d3.geoArea({ type: 'Polygon', coordinates: rings }) > 2 * Math.PI) rings.forEach(r => r.reverse());
  }
}

// ------------------------------------------------------------------ carga inicial
async function init() {
  const [summary, ufTopo, munTopo, zonaTopo] = await Promise.all([
    fetchJSON('data/summary.json'), fetchJSON('data/geo/uf.json'), fetchJSON('data/geo/mun.json'),
    fetchJSON('data/geo/zonas.json'),
  ]);
  S = summary;
  // IBGE -> TSE
  const ibge2tse = {};
  for (const [id, e] of Object.entries(S.el)) if (e.ibge) ibge2tse[e.ibge] = id;
  const UF_IBGE = { 11: 'ro', 12: 'ac', 13: 'am', 14: 'rr', 15: 'pa', 16: 'ap', 17: 'to', 21: 'ma', 22: 'pi', 23: 'ce', 24: 'rn', 25: 'pb',
    26: 'pe', 27: 'al', 28: 'se', 29: 'ba', 31: 'mg', 32: 'es', 33: 'rj', 35: 'sp', 41: 'pr', 42: 'sc', 43: 'rs', 50: 'ms', 51: 'mt', 52: 'go', 53: 'df' };
  const ufObj = Object.values(ufTopo.objects)[0];
  const munObj = Object.values(munTopo.objects)[0];
  const ufFeats = topojson.feature(ufTopo, ufObj).features;
  ufFeats.forEach(f => f.id = UF_IBGE[f.properties.codarea]);
  const munFeats = topojson.feature(munTopo, munObj).features;
  munFeats.forEach(f => f.id = ibge2tse[f.properties.codarea]);
  const zonaObj = Object.values(zonaTopo.objects)[0];
  const zonaFeats = topojson.feature(zonaTopo, zonaObj).features;
  zonaFeats.forEach(f => { f.id = f.properties.id; rewind(f); });
  const brFeat = { type: 'Feature', id: 'br', geometry: topojson.merge(ufTopo, ufObj.geometries) };
  const ufMesh = topojson.mesh(ufTopo, ufObj, (a, b) => a !== b);
  const brOutline = topojson.mesh(ufTopo, ufObj, (a, b) => a === b);

  projection = d3.geoMercator().fitExtent([[40, 40], [1000 - 40, 1000 - 40]], brFeat);
  baseScale = projection.scale();
  const mk = feats => feats.filter(f => f.id).map(f => {
    const p = new Path2D(); d3.geoPath(projection, p)(f);
    const [[x0, y0], [x1, y1]] = d3.geoPath(projection).bounds(f);
    return { id: f.id, path: p, bbox: [x0, y0, x1, y1], area: (x1 - x0) * (y1 - y0) };
  });
  geo.pais = mk([brFeat]);
  // Exterior: elemento físico no mapa, um círculo no Atlântico (canto inferior direito do enquadramento)
  const EX = { cx: 880, cy: 860, r: 58 };
  const exPath = new Path2D(); exPath.arc(EX.cx, EX.cy, EX.r, 0, 2 * Math.PI);
  const exLines = new Path2D();
  exLines.ellipse(EX.cx, EX.cy, EX.r * 0.45, EX.r, 0, 0, 2 * Math.PI);
  exLines.moveTo(EX.cx, EX.cy - EX.r); exLines.lineTo(EX.cx, EX.cy + EX.r);
  for (const f of [-0.45, 0, 0.45]) {
    const y = EX.cy + f * EX.r, hw = Math.sqrt(1 - f * f) * EX.r;
    exLines.moveTo(EX.cx - hw, y); exLines.lineTo(EX.cx + hw, y);
  }
  const exterior = { id: 'zz', path: exPath, bbox: [EX.cx - EX.r, EX.cy - EX.r, EX.cx + EX.r, EX.cy + EX.r], area: Math.PI * EX.r ** 2, ex: EX };
  geo.exterior = exterior; geo.exLines = exLines;
  geo.estado = mk(ufFeats).concat(exterior);
  geo.municipio = mk(munFeats).concat(exterior);
  geo.zona = mk(zonaFeats).concat(exterior);
  geo.zonaMesh = new Path2D(); d3.geoPath(projection, geo.zonaMesh)(topojson.mesh(zonaTopo, zonaObj, (a, b) => a !== b));
  geo.ufMesh = new Path2D(); d3.geoPath(projection, geo.ufMesh)(ufMesh);
  geo.outline = new Path2D(); d3.geoPath(projection, geo.outline)(brOutline);
  geo.munMesh = new Path2D(); d3.geoPath(projection, geo.munMesh)(topojson.mesh(munTopo, munObj, (a, b) => a !== b));

  buildMapmodes();
  setupMapmodesCollapse();
  setupZoom();
  setupUI();
  setupGeoSearch();
  updateScale();
  resize();
  fitView();
  $('#loading').hidden = true;
}

// ------------------------------------------------------------------ zoom
let zoom;
function fitView() {
  const pad = 20;
  const avW = W - (state.selected ? 440 : 0);
  const k = Math.min((avW - 2 * pad) / 1000, (H - 2 * pad) / 1000);
  const t = d3.zoomIdentity.translate((avW - 1000 * k) / 2, (H - 1000 * k) / 2).scale(k);
  d3.select(canvas).call(zoom.transform, t);
}
function setupZoom() {
  zoom = d3.zoom().scaleExtent([0.06, 6000])
    .on('start', ev => { if (ev.sourceEvent && ev.sourceEvent.type === 'mousedown') canvas.classList.add('dragging'); })
    .on('zoom', ev => { state.transform = ev.transform; scheduleZoomDraw(); hideTooltip(); })
    .on('end', () => canvas.classList.remove('dragging'));
  d3.select(canvas).call(zoom).on('dblclick.zoom', null);
}

let rafPending = false;
function scheduleDraw() {
  if (rafPending) return;
  rafPending = true;
  requestAnimationFrame(() => { rafPending = false; draw(); });
}
// Durante zoom/arraste: se o desenho completo é lento, reaproveita a última imagem
// (transformada) e só redesenha tudo quando o movimento para.
let zoomRaf = false, zoomIdle = null;
function scheduleZoomDraw() {
  if (lastDrawMs < 35 || !snapT) { scheduleDraw(); return; }
  if (!zoomRaf) {
    zoomRaf = true;
    requestAnimationFrame(() => { zoomRaf = false; quickDraw(); });
  }
  clearTimeout(zoomIdle);
  zoomIdle = setTimeout(draw, 160);
}
function quickDraw() {
  const t = state.transform, s = t.k / snapT.k;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = '#0b0e13';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.setTransform(s, 0, 0, s, DPR * (t.x - s * snapT.x), DPR * (t.y - s * snapT.y));
  ctx.drawImage(snap, 0, 0);
  drawOverlay();
}
let ovRaf = false;
function scheduleOverlay() {
  if (ovRaf) return;
  ovRaf = true;
  requestAnimationFrame(() => { ovRaf = false; drawOverlay(); });
}
function drawOverlay() {
  const t = state.transform, px = 1 / t.k;
  octx.setTransform(1, 0, 0, 1, 0, 0);
  octx.clearRect(0, 0, overlay.width, overlay.height);
  if (!projection) return;
  octx.setTransform(DPR * t.k, 0, 0, DPR * t.k, DPR * t.x, DPR * t.y);
  if (searchPin) {
    // alfinete do endereço buscado: ponta no ponto, tamanho fixo na tela. Amarelo forte com
    // contorno escuro e halo, para destacar sobre o azul/vermelho do mapa e sobre o fundo escuro.
    const [x, y] = projection([searchPin.lon, searchPin.lat]);
    const u = px, R = 13 * u, H = 40 * u, cy = y - H + R;   // raio da cabeça, altura total, centro da cabeça
    const a = Math.asin(R / (H - R));                        // ângulo onde as laterais tangenciam a cabeça
    const pin = new Path2D();
    pin.moveTo(x, y);
    pin.arc(x, cy, R, Math.PI / 2 + a, Math.PI / 2 - a);
    pin.closePath();
    octx.beginPath(); octx.ellipse(x, y, 8 * u, 3 * u, 0, 0, 2 * Math.PI);   // sombra no chão
    octx.fillStyle = 'rgba(0,0,0,.6)'; octx.fill();
    octx.save();
    octx.shadowColor = 'rgba(255,214,10,.7)'; octx.shadowBlur = 14;          // halo
    octx.fillStyle = '#ffd60a'; octx.fill(pin);
    octx.restore();
    octx.strokeStyle = '#0b0e13'; octx.lineWidth = 2.5 * u; octx.stroke(pin);
    octx.beginPath(); octx.arc(x, cy, R * 0.42, 0, 2 * Math.PI);
    octx.fillStyle = '#0b0e13'; octx.fill();
  }
  for (const [id, col, w] of [[state.hover, 'rgba(255,255,255,.8)', 1.5], [state.selected, '#fff', 2.5]]) {
    if (id == null) continue;
    octx.strokeStyle = col; octx.lineWidth = w * px;
    if (typeof id === 'number') {
      if (!locais) continue;
      const r = locais.radius(t.k) * px;
      octx.beginPath(); octx.arc(locais.X[id], locais.Y[id], r + 1.5 * px, 0, 2 * Math.PI); octx.stroke();
      continue;
    }
    if (typeof id === 'string' && id[0] === 'x' && extCities) {
      const b = extCities.get(id), r = extRadius(t.k) * px;
      octx.beginPath(); octx.arc(b.x, b.y, r + 1.5 * px, 0, 2 * Math.PI); octx.stroke();
      continue;
    }
    const g = (geo[state.level] || [geo.exterior]).find(f => f.id === id);
    if (g) octx.stroke(g.path);
  }
}

// ------------------------------------------------------------------ escalas
// Limites a partir dos dados do nível atual (percentis), nunca 0%/100% fixos.
let scale = null;
function currentElements() {
  const ids = state.level === 'pais' ? ['br'] : geo[state.level].map(g => g.id);
  return ids.map(id => [id, S.el[id]]).filter(([, e]) => e);
}
function metricValues() {
  const m = METRIC[state.metric];
  if (state.level === 'secao') {
    if (!locais) return [];
    const out = locais.values(m);
    for (const b of extCities.values()) { const v = m.get(b.e); if (v != null && isFinite(v)) out.push(v); }
    return out;
  }
  return currentElements().map(([, e]) => m.get(e)).filter(v => v != null && isFinite(v));
}

const SEQ = d3.interpolatePlasma;         // azul-escuro → roxo → rosa → laranja → amarelo
const DIV = t => d3.interpolatePuOr(t);   // queda = roxo, alta = laranja
const PRES = t => d3.interpolateRdBu(1 - t);       // 0 = PL (azul), 1 = PT (vermelho)
const NO_DATA = '#3a404c';
const GOV_BASE = d3.rgb('#252a33');

function updateScale() {
  const m = METRIC[state.metric];
  const vals = metricValues().slice().sort((a, b) => a - b);
  const single = state.level === 'pais';
  let sc = { kind: m.kind };
  if (m.kind === 'abs') {
    const pos = vals.filter(v => v > 0);
    let lo = quantile(pos, 0.02), hi = quantile(pos, 0.98);
    if (single || !(hi > lo)) { lo = (pos[0] || 1) / 2; hi = (pos[pos.length - 1] || 2) * 2; }
    const l = d3.scaleLog().domain([lo, hi]).clamp(true);
    sc.color = v => v > 0 ? SEQ(l(v)) : NO_DATA;
    sc.lo = lo; sc.hi = hi; sc.ramp = SEQ; sc.fmt = fmtCompact;
  } else if (m.kind === 'pct') {
    let lo = quantile(vals, 0.02), hi = quantile(vals, 0.98);
    if (single || !(hi > lo)) { const v = vals[0] || 0.5; lo = v - 0.05; hi = v + 0.05; }
    lo = Math.floor(lo * 100) / 100; hi = Math.ceil(hi * 100) / 100;
    const l = d3.scaleLinear().domain([lo, hi]).clamp(true);
    sc.color = v => SEQ(l(v)); sc.lo = lo; sc.hi = hi; sc.ramp = SEQ; sc.fmt = v => fmtPct(v, 0);
  } else if (['rel', 'pp', 'dpres', 'pres'].includes(m.kind)) {
    const center = m.kind === 'pres' ? 0.5 : 0;
    let ext;
    if (m.kind === 'pres') {
      // presidente: limites nos percentis 25–75, simétricos em torno de 50% (empate = cor neutra)
      ext = Math.max(Math.abs(quantile(vals, 0.25) - center), Math.abs(quantile(vals, 0.75) - center));
    } else {
      const dev = vals.map(v => Math.abs(v - center)).sort((a, b) => a - b);
      ext = quantile(dev, 0.98);
    }
    if (single || !(ext > 0)) ext = Math.max(Math.abs((vals[0] ?? center) - center) * 1.5, 0.01);
    ext = niceUp(ext * 100) / 100;
    const l = d3.scaleLinear().domain([center - ext, center + ext]).clamp(true);
    const ramp = m.kind === 'pres' || m.kind === 'dpres' ? PRES : DIV;
    sc.color = v => ramp(l(v)); sc.lo = center - ext; sc.hi = center + ext; sc.center = center; sc.ramp = ramp;
    sc.fmt = m.kind === 'pres' ? (v => fmtPct(v, 0)) : (v => fmtPP(v, ext < 0.05 ? 1 : 0) + (m.kind === 'rel' ? '%' : ' p.p.'));
    if (m.kind === 'pres') sc.labels = ['PL', 'PT'];
    if (m.kind === 'dpres') sc.labels = ['→ PL', '→ PT'];
  } else if (m.kind === 'gov') {
    let hi = quantile(vals, 0.95);
    if (single || !(hi > 0)) hi = Math.max(vals[0] || 0.2, 0.05);
    hi = niceUp(hi * 100) / 100;
    const l = d3.scaleLinear().domain([0, hi]).clamp(true);
    sc.colorFor = (party, margin) => d3.interpolateRgb(GOV_BASE, partyColor(party))(0.3 + 0.7 * l(margin));
    sc.hi = hi;
    sc.parties = state.level === 'secao' ? (locais ? locais.govParties() : []) : [...new Set(currentElements().map(([, e]) => e.g && e.g[0]).filter(Boolean))];
  }
  scale = sc;
  renderLegend();
}

function colorOf(e) {
  if (!e) return NO_DATA;
  const m = METRIC[state.metric];
  if (m.kind === 'gov') return e.g ? scale.colorFor(e.g[0], e.g[1]) : NO_DATA;
  const v = m.get(e);
  return v == null || !isFinite(v) ? NO_DATA : scale.color(v);
}

function renderLegend() {
  const m = METRIC[state.metric];
  $('#mm-title').textContent = m.name;
  const L = $('#legend');
  if (m.kind === 'gov') {
    const ps = (scale.parties || []).slice().sort();
    L.innerHTML = `<div class="swatches">${ps.map(p => `<span class="sw"><i style="background:${partyColor(p)}"></i>${esc(p)}</span>`).join('')}</div>
      <div class="note">Intensidade = margem de vitória (cor plena ≥ ${fmtPct(scale.hi, 0)} dos válidos)</div>`;
    return;
  }
  const stops = d3.range(0, 1.0001, 0.1).map(t => scale.ramp(t)).join(',');
  const mid = scale.center != null ? scale.fmt(scale.center).replace(/^[+−]/, '') : '';
  const lab = scale.labels || ['', ''];
  L.innerHTML = `<div class="bar" style="background:linear-gradient(90deg,${stops})"></div>
    <div class="ticks"><span>≤ ${scale.fmt(scale.lo)} ${lab[0]}</span>${mid ? `<span>${mid}</span>` : ''}<span>≥ ${scale.fmt(scale.hi)} ${lab[1]}</span></div>
    ${m.kind === 'abs' ? '<div class="note">Escala logarítmica</div>' : ''}
    ${m.kind === 'dpres' ? '<div class="note">Variação da fatia do PT nos votos PT+PL</div>' : ''}
    ${m.kind === 'pres' ? '<div class="note">Fatia do PT nos votos PT+PL</div>' : ''}`;
}

// ------------------------------------------------------------------ desenho
function draw() {
  if (!projection || !scale) return;
  clearTimeout(zoomIdle);
  const t0 = performance.now();
  const t = state.transform;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--sea') || '#0b0e13';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.setTransform(DPR * t.k, 0, 0, DPR * t.k, DPR * t.x, DPR * t.y);
  const px = 1 / t.k;  // 1 pixel de tela em coordenadas do mapa
  // recorte de visibilidade
  const vx0 = -t.x / t.k, vy0 = -t.y / t.k, vx1 = (W - t.x) / t.k, vy1 = (H - t.y) / t.k;
  const visible = b => !(b[2] < vx0 || b[0] > vx1 || b[3] < vy0 || b[1] > vy1);

  if (state.level === 'secao') {
    if (worldBase) {
      ctx.fillStyle = '#161a21'; ctx.fill(worldBase.land);
      ctx.strokeStyle = 'rgba(255,255,255,.1)'; ctx.lineWidth = 0.6 * px; ctx.stroke(worldBase.borders);
    }
    for (const g of geo.estado) { if (g.id !== 'zz') { ctx.fillStyle = '#1b2029'; ctx.fill(g.path); } }
    if (showStreets) drawTiles(ctx, t, [vx0, vy0, vx1, vy1]);
    // contorno dos municípios (mais visível conforme o zoom aumenta)
    ctx.strokeStyle = `rgba(255,255,255,${Math.min(0.38, 0.17 + 0.035 * Math.log2(Math.max(1, t.k)))})`;
    ctx.lineWidth = 0.6 * px; ctx.stroke(geo.munMesh);
    if (locais) locais.draw(ctx, t, px, [vx0, vy0, vx1, vy1]);
    ctx.strokeStyle = 'rgba(255,255,255,.4)'; ctx.lineWidth = 1 * px; ctx.stroke(geo.ufMesh);
    if (extCities) drawExtCities(ctx, t, px, [vx0, vy0, vx1, vy1]);
  }
  const feats = state.level === 'secao' ? [] : geo[state.level];
  for (const g of feats) {
    if (!visible(g.bbox)) continue;
    ctx.fillStyle = colorOf(S.el[g.id]);
    ctx.fill(g.path);
  }
  // nos níveis de polígonos, as ruas ficam por cima das cores como linhas claras
  if (feats.length && showStreets) drawTiles(ctx, t, [vx0, vy0, vx1, vy1]);
  if (state.level === 'zona') {
    // divisória bem clara entre municípios dentro da mesma zona; bordas das zonas por cima
    ctx.strokeStyle = 'rgba(255,255,255,.22)'; ctx.lineWidth = 0.5 * px; ctx.stroke(geo.munMesh);
    ctx.strokeStyle = 'rgba(14,17,22,.8)'; ctx.lineWidth = 0.7 * px; ctx.stroke(geo.zonaMesh);
    ctx.strokeStyle = 'rgba(14,17,22,.95)'; ctx.lineWidth = 1.4 * px; ctx.stroke(geo.ufMesh);
  } else if (state.level === 'municipio') {
    ctx.strokeStyle = 'rgba(14,17,22,.55)'; ctx.lineWidth = 0.5 * px; ctx.stroke(geo.munMesh);
    ctx.strokeStyle = 'rgba(14,17,22,.95)'; ctx.lineWidth = 1.4 * px; ctx.stroke(geo.ufMesh);
  } else if (state.level === 'estado') {
    ctx.strokeStyle = 'rgba(14,17,22,.95)'; ctx.lineWidth = 1.2 * px; ctx.stroke(geo.ufMesh);
  }
  ctx.strokeStyle = 'rgba(255,255,255,.25)'; ctx.lineWidth = 1 * px; ctx.stroke(geo.outline);
  // no nível Seção o exterior aparece como pontos no mapa, sem o círculo
  if (state.level !== 'pais' && !(state.level === 'secao' && extCities)) drawExterior(ctx, px);
  snapCtx.setTransform(1, 0, 0, 1, 0, 0);
  snapCtx.clearRect(0, 0, snap.width, snap.height);
  snapCtx.drawImage(canvas, 0, 0);
  snapT = { k: t.k, x: t.x, y: t.y };
  lastDrawMs = performance.now() - t0;
  drawOverlay();
}

function drawExterior(c, px) {
  const ex = geo.exterior;
  if (!(state.level === 'secao' && extCities)) {
    c.strokeStyle = 'rgba(14,17,22,.55)'; c.lineWidth = 1.2 * px; c.stroke(geo.exLines);
  }
  c.strokeStyle = 'rgba(255,255,255,.45)'; c.lineWidth = 1.2 * px; c.stroke(ex.path);
  c.font = `500 ${13 * px}px Roboto, system-ui, sans-serif`;   // tamanho fixo na tela
  c.fillStyle = '#a7afbd'; c.textAlign = 'center'; c.textBaseline = 'top';
  c.fillText('Exterior', ex.ex.cx, ex.ex.cy + ex.ex.r + 6 * px);
}


// ------------------------------------------------------------------ fundo OpenStreetMap
// Tiles padrão do OpenStreetMap convertidos em linhas claras sobre fundo transparente:
// cinza invertido (ruas claras viram escuras, fundo claro vira transparente) com opacidade
// baixa, para um contorno bem claro das ruas (no fundo do nível Seção e por cima das cores nos
// demais). A projeção do app é Mercator, a mesma dos tiles. Pode ser desligado no painel de filtros.
const tileCache = new Map();
let tileRedraw = null;
let showStreets = true;
try { showStreets = localStorage.getItem('mapa-tse:ruas') !== '0'; } catch (e) { /* sem storage */ }
function processTile(img) {
  const c = document.createElement('canvas');
  c.width = img.naturalWidth; c.height = img.naturalHeight;
  const g = c.getContext('2d');
  g.drawImage(img, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height), a = d.data;
  for (let i = 0; i < a.length; i += 4) {
    const L = 0.299 * a[i] + 0.587 * a[i + 1] + 0.114 * a[i + 2];
    // fundo do OSM é claro (~240): quanto mais escuro o traço original, mais visível aqui
    const v = Math.max(0, Math.min(1, (232 - L) / 140));
    a[i] = a[i + 1] = a[i + 2] = 235;
    a[i + 3] = Math.round(v * 70);
  }
  g.putImageData(d, 0, 0);
  return c;
}
function tileImage(z, x, y) {
  const key = `${z}/${x}/${y}`;
  let t = tileCache.get(key);
  if (!t) {
    t = { canvas: null };
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      try { t.canvas = processTile(img); } catch (e) { return; }
      clearTimeout(tileRedraw); tileRedraw = setTimeout(draw, 120);
    };
    img.src = `https://tile.openstreetmap.org/${z}/${x}/${y}.png`;
    tileCache.set(key, t);
    if (tileCache.size > 500) tileCache.delete(tileCache.keys().next().value);
  }
  return t.canvas;
}
function drawTiles(c, t, [vx0, vy0, vx1, vy1]) {
  const s = projection.scale(), [tx, ty] = projection.translate();
  // nível de zoom do tile pelo tamanho na tela (considerando a densidade de pixels)
  const z = Math.max(0, Math.min(19, Math.round(Math.log2(s * t.k * DPR * 2 * Math.PI / 256))));
  const n = 2 ** z, size = 2 * Math.PI * s / n;          // tamanho do tile em coordenadas do mapa
  const ox = tx - Math.PI * s, oy = ty - Math.PI * s;      // canto (0,0) do mundo Mercator
  const x0 = Math.max(0, Math.floor((vx0 - ox) / size)), x1 = Math.min(n - 1, Math.floor((vx1 - ox) / size));
  const y0 = Math.max(0, Math.floor((vy0 - oy) / size)), y1 = Math.min(n - 1, Math.floor((vy1 - oy) / size));
  if ((x1 - x0 + 1) * (y1 - y0 + 1) > 400) return;
  c.save();
  c.imageSmoothingEnabled = true;
  for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
    const img = tileImage(z, x, y);
    if (img) c.drawImage(img, ox + x * size, oy + y * size, size + 0.5 / t.k, size + 0.5 / t.k);
  }
  c.restore();
}

// ------------------------------------------------------------------ seções
// Um ponto por local de votação (seções no mesmo local agrupadas no build).
async function loadLocais() {
  if (locais) return locais;
  const ufs = Object.keys(S.uf).filter(u => u !== 'zz');
  let done = 0;
  $('#loading').hidden = false;
  $('#loading-text').textContent = `Carregando seções… 0/${ufs.length}`;
  const [parts, zzCities] = await Promise.all([
    Promise.all(ufs.map(uf => fetchJSON(`data/s/${uf}.json`).then(d => {
      done++; $('#loading-text').textContent = `Carregando seções… ${done}/${ufs.length}`; d.uf = uf; return d;
    }))),
    fetchJSON('data/s/zz.json'),
  ]);
  const world = await fetchJSON('data/geo/world.json');
  $('#loading').hidden = true;
  buildExtCities(zzCities, world);
  const N = parts.reduce((a, p) => a + p.ns.length, 0);
  const X = new Float32Array(N), Y = new Float32Array(N);
  const cols = ['apt', 'comp', 'val', 'bra', 'nul', 'pt', 'pl', 'gm'];
  const A = Object.fromEntries(cols.map(c => [c, new Int32Array(N)]));
  const GP = new Array(N), REF = new Int32Array(N), PART = new Uint8Array(N);
  let i = 0;
  parts.forEach((p, pi) => {
    for (let j = 0; j < p.ns.length; j++, i++) {
      const [x, y] = projection([p.lon[j] / 1e5, p.lat[j] / 1e5]);
      X[i] = x; Y[i] = y;
      for (const c of cols) A[c][i] = p[c][j];
      GP[i] = p.gp[j] >= 0 ? p.parties[p.gp[j]] : null;
      REF[i] = j; PART[i] = pi;
    }
  });
  // grade espacial para o hover
  const CELL = 2, grid = new Map();
  for (let k = 0; k < N; k++) {
    const key = Math.floor(X[k] / CELL) + ',' + Math.floor(Y[k] / CELL);
    let arr = grid.get(key); if (!arr) grid.set(key, arr = []); arr.push(k);
  }
  const elemOf = k => ({
    t26: [A.apt[k], A.comp[k], A.val[k], A.bra[k], A.nul[k]], t22: null,
    p26: [A.pt[k], A.pl[k]], p22: null, g: GP[k] ? [GP[k], A.gm[k] / 1000] : null,
  });
  const radiusPx = k => Math.min(8, 1.1 + Math.log2(Math.max(1, k)) * 0.8);
  locais = {
    N, X, Y,
    elem: elemOf,
    radius: radiusPx,
    values(m) { const out = []; for (let k = 0; k < N; k++) { const v = m.get(elemOf(k)); if (v != null && isFinite(v)) out.push(v); } return out; },
    govParties() { return [...new Set(GP.filter(Boolean))]; },
    info(k) {
      const p = parts[PART[k]], j = REF[k], mun = p.muns[p.m[j]];
      return { uf: p.uf, mun, idx: j, ns: p.ns[j], z: p.z[j], name: p.names[j], munName: S.el[mun] ? S.el[mun].n : mun };
    },
    colors: null,
    recolor() {
      const by = new Map();
      for (let k = 0; k < N; k++) { const c = colorOf(elemOf(k)); let a = by.get(c); if (!a) by.set(c, a = []); a.push(k); }
      this.colors = by;
    },
    draw(c, t, px, [vx0, vy0, vx1, vy1]) {
      if (!this.colors) this.recolor();
      const r = radiusPx(t.k) * px;
      for (const [col, idx] of this.colors) {
        c.fillStyle = col;
        c.beginPath();
        for (const k of idx) {
          const x = X[k], y = Y[k];
          if (x < vx0 || x > vx1 || y < vy0 || y > vy1) continue;
          c.moveTo(x + r, y); c.arc(x, y, r, 0, 2 * Math.PI);
        }
        c.fill();
      }
    },
    nearest(mx, my, maxDist) {
      let best = -1, bd = maxDist * maxDist;
      const rr = Math.ceil(maxDist / CELL), cx = Math.floor(mx / CELL), cy = Math.floor(my / CELL);
      for (let gx = cx - rr; gx <= cx + rr; gx++) for (let gy = cy - rr; gy <= cy + rr; gy++) {
        const arr = grid.get(gx + ',' + gy); if (!arr) continue;
        for (const k of arr) { const d = (X[k] - mx) ** 2 + (Y[k] - my) ** 2; if (d < bd) { bd = d; best = k; } }
      }
      return best;
    },
  };
  return locais;
}

// Exterior no nível Seção: cada local de votação no exterior é um ponto na posição real, no
// próprio mapa (mesma projeção), com os continentes ao fundo. O TSE não publica as coordenadas
// desses locais; elas foram geocodificadas a partir dos endereços (tools/geocode_exterior.py).
function buildExtCities(list, world) {
  const obj = world.objects.countries;
  const land = new Path2D(); d3.geoPath(projection, land)(topojson.feature(world, obj));
  const borders = new Path2D(); d3.geoPath(projection, borders)(topojson.mesh(world, obj, (a, b) => a !== b));
  worldBase = { land, borders };
  extCities = new Map();
  list.forEach((p, i) => {
    const [x, y] = projection([p.lon, p.lat]);
    const v = p.v;
    extCities.set('x' + i, { x, y, c: p, e: { t26: p.t, t22: null, p26: [v['13'] || 0, v['22'] || 0], p22: null, g: null } });
  });
}
// pontos do exterior são poucos e espalhados: tamanho mínimo de 3 px para serem achados
const extRadius = k => Math.max(3, locais.radius(k));
function drawExtCities(c, t, px, [vx0, vy0, vx1, vy1]) {
  const r = extRadius(t.k) * px;
  for (const b of extCities.values()) {
    if (b.x < vx0 || b.x > vx1 || b.y < vy0 || b.y > vy1) continue;
    c.beginPath(); c.arc(b.x, b.y, r, 0, 2 * Math.PI);
    c.fillStyle = colorOf(b.e); c.fill();
  }
}

// ------------------------------------------------------------------ hit test
function pick(mx, my) {
  const t = state.transform;
  const x = (mx - t.x) / t.k, y = (my - t.y) / t.k;
  if (state.level === 'secao' && extCities) {
    let best = null, bd = (8 / t.k) ** 2;
    for (const [id, b] of extCities) { const d = (x - b.x) ** 2 + (y - b.y) ** 2; if (d < bd) { bd = d; best = id; } }
    if (best) return best;
  } else if (state.level !== 'pais') {
    const e = geo.exterior.ex;
    if ((x - e.cx) ** 2 + (y - e.cy) ** 2 <= e.r ** 2) return 'zz';
  }
  if (state.level === 'secao') {
    if (!locais) return null;
    const k = locais.nearest(x, y, 8 / t.k);   // raio de captura de ~8 px de tela
    return k >= 0 ? k : null;
  }
  const feats = geo[state.level];
  let best = null;
  for (const g of feats) {
    const b = g.bbox;
    if (x < b[0] || x > b[2] || y < b[1] || y > b[3]) continue;
    if (hitCtx.isPointInPath(g.path, x, y) && (!best || g.area < best.area)) best = g;
  }
  return best ? best.id : null;
}

// ------------------------------------------------------------------ tooltip
const tip = $('#tooltip');
function hideTooltip() { tip.hidden = true; }
function metricText(e) {
  const m = METRIC[state.metric];
  if (!e) return 'Sem dados';
  if (m.kind === 'gov') {
    if (!e.g) return 'Sem dados';
    return `<b style="color:${partyColor(e.g[0])}">${esc(e.g[0])}</b> · margem ${fmtPct(e.g[1], 1)}`;
  }
  const v = m.get(e);
  if (v == null || !isFinite(v)) return m.diff ? (state.level === 'secao' ? 'Sem comparação com 2022 por seção' : 'Sem dados de 2022') : 'Sem dados';
  switch (m.kind) {
    case 'abs': return `<b>${fmtInt.format(v)}</b>`;
    case 'pct': return `<b>${fmtPct(v)}</b>`;
    case 'rel': return `<b>${fmtPP(v, 2)}%</b>`;
    case 'pp': return `<b>${fmtPP(v, 2)} p.p.</b>`;
    case 'pres': {
      // porcentagens reais sobre os votos válidos (a cor usa só a disputa PT × PL)
      const val = e.t26 && e.t26[2];
      if (!val) return `PT <b>${fmtPct(v, 1)}</b> · PL <b>${fmtPct(1 - v, 1)}</b> (PT+PL)`;
      return `PT <b>${fmtPct(e.p26[0] / val, 1)}</b> · PL <b>${fmtPct(e.p26[1] / val, 1)}</b> <span class="tt-sub">dos válidos</span>`;
    }
    case 'dpres': return `<b>${fmtPP(v, 2)} p.p.</b> ${v >= 0 ? 'para o PT' : 'para o PL'}`;
  }
  return '';
}
function zoneMuns(e, max = 3) {
  const ns = e.muns.map(m => titleCase(S.el[m] ? S.el[m].n : m));
  return ns.length > max ? ns.slice(0, max).join(', ') + ` +${ns.length - max}` : ns.join(', ');
}
function showTooltip(mx, my, id) {
  let e = S.el[id], name, sub;
  if (typeof id === 'string' && id[0] === 'x') {
    const b = extCities.get(id);
    e = b.e;
    name = titleCase(b.c.n);
    sub = `${titleCase(b.c.city)} · ${b.c.ns} ${b.c.ns > 1 ? 'seções' : 'seção'}${b.c.aprox ? ' · posição aproximada' : ''}`;
  } else if (typeof id === 'number') {
    const inf = locais.info(id);
    e = locais.elem(id);
    name = titleCase(inf.name || 'Local de votação');
    sub = `${titleCase(inf.munName)} (${inf.uf.toUpperCase()}) · Zona ${inf.z} · ${inf.ns} ${inf.ns > 1 ? 'seções' : 'seção'}`;
  } else if (e && e.muns) {
    name = e.n;
    sub = `${zoneMuns(e)} (${e.uf.toUpperCase()})`;
  } else {
    name = id === 'br' ? 'Brasil' : id === 'zz' ? 'Exterior' : titleCase(e ? e.n : id);
    sub = e && e.uf && e.uf !== id && id !== 'br' ? e.uf.toUpperCase() : '';
  }
  tip.innerHTML = `<div class="tt-name">${esc(name)}</div>${sub ? `<div class="tt-sub">${esc(sub)}</div>` : ''}
    <div class="tt-val">${metricText(e)}</div>`;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let x = mx + 14, y = my + 14;
  if (x + r.width > W - 8) x = mx - r.width - 14;
  if (y + r.height > H - 8) y = my - r.height - 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}

// ------------------------------------------------------------------ UI
function buildMapmodes() {
  const grid = $('#mm-grid');
  let html = '', group = '';
  for (const m of METRICS) {
    if (m.group !== group) { group = m.group; html += `<div class="mm-group-label">${group}</div>`; }
    html += `<button class="mm-btn" data-metric="${m.id}" title="${esc(m.name)}" aria-label="${esc(m.name)}">
      <svg viewBox="0 0 24 24">${ICONS[m.icon]}</svg>${m.diff ? '<span class="delta">Δ</span>' : ''}</button>`;
  }
  grid.innerHTML = html;
  grid.addEventListener('click', ev => {
    const b = ev.target.closest('.mm-btn'); if (!b || b.disabled) return;
    setMetric(b.dataset.metric);
  });
  syncMapmodes();
}
// No celular o painel de filtros de mapa ocupa muito espaço: começa recolhido (só legenda e
// título) e um botão abre/fecha. No computador o botão nem aparece (CSS).
function setupMapmodesCollapse() {
  const box = $('#mapmodes'), btn = $('#mm-collapse');
  if (!box || !btn) return;   // HTML antigo em cache: segue sem o botão
  const mobile = window.matchMedia('(max-width: 760px)');
  const set = collapsed => {
    box.classList.toggle('collapsed', collapsed);
    btn.textContent = collapsed ? 'Mostrar filtros' : 'Esconder filtros';
    btn.setAttribute('aria-expanded', String(!collapsed));
  };
  set(mobile.matches);
  btn.addEventListener('click', () => set(!box.classList.contains('collapsed')));
  // ao virar para o computador (ou girar a tela larga), mostra tudo de novo
  const onChange = e => { if (!e.matches) set(false); };
  if (mobile.addEventListener) mobile.addEventListener('change', onChange);
  else if (mobile.addListener) mobile.addListener(onChange);   // Safari antigo
}
function syncMapmodes() {
  document.querySelectorAll('.mm-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.metric === state.metric);
    b.disabled = state.level === 'secao' && METRIC[b.dataset.metric].diff;
    b.title = METRIC[b.dataset.metric].name + (b.disabled ? ' (sem comparação com 2022 por seção)' : '');
  });
}
function setMetric(id) {
  state.metric = id;
  if (locais) locais.colors = null;
  syncMapmodes(); updateScale(); draw();
}
async function setLevel(lv) {
  if (lv === state.level) return;
  state.level = lv;
  document.querySelectorAll('.levels button').forEach(b => b.classList.toggle('active', b.dataset.level === lv));
  state.hover = null;
  closePanel();
  if (lv === 'secao') {
    if (METRIC[state.metric].diff) state.metric = 'pres';
    await loadLocais();
    locais.colors = null;
  }
  syncMapmodes(); updateScale(); draw();
}

function setupUI() {
  document.querySelectorAll('.levels button').forEach(b => b.addEventListener('click', () => setLevel(b.dataset.level)));
  $('#panel-close').addEventListener('click', closePanel);
  const st = $('#streets');
  if (st) {   // HTML antigo em cache pode não ter a opção de ruas
    st.checked = showStreets;
    if ($('#attribution')) $('#attribution').hidden = !showStreets;
    st.addEventListener('change', () => {
      showStreets = st.checked;
      try { localStorage.setItem('mapa-tse:ruas', showStreets ? '1' : '0'); } catch (e) { /* sem storage */ }
      if ($('#attribution')) $('#attribution').hidden = !showStreets;
      draw();
    });
  }
  window.addEventListener('resize', resize);
  window.addEventListener('keydown', ev => { if (ev.key === 'Escape') closePanel(); });

  let down = null;
  canvas.addEventListener('mousedown', ev => { down = [ev.clientX, ev.clientY]; });
  canvas.addEventListener('mousemove', ev => {
    const id = pick(ev.clientX, ev.clientY);
    if (id !== state.hover) { state.hover = id; scheduleOverlay(); }
    canvas.classList.toggle('hovering', id != null);
    if (id != null) showTooltip(ev.clientX, ev.clientY, id); else hideTooltip();
  });
  canvas.addEventListener('mouseleave', () => { state.hover = null; hideTooltip(); scheduleOverlay(); });
  canvas.addEventListener('click', ev => {
    if (down && Math.hypot(ev.clientX - down[0], ev.clientY - down[1]) > 4) return;
    const id = pick(ev.clientX, ev.clientY);
    if (id != null) { hideTooltip(); openPanel(id); }
  });
}

// ------------------------------------------------------------------ busca de endereços
// Nominatim (OpenStreetMap). Só busca ao enviar (Enter), como pede a política de uso do serviço.
let searchPin = null;
function setupGeoSearch() {
  const form = $('#geosearch'), input = $('#geosearch-q'), out = $('#geosearch-results'), clear = $('#geosearch-clear');
  if (!form || !input || !out || !clear) return;   // HTML antigo em cache
  let results = [];
  const close = () => { out.hidden = true; };
  input.addEventListener('input', () => { clear.hidden = !input.value; });
  clear.addEventListener('click', () => { input.value = ''; clear.hidden = true; close(); searchPin = null; drawOverlay(); input.focus(); });
  document.addEventListener('click', ev => { if (!form.contains(ev.target)) close(); });
  input.addEventListener('keydown', ev => { if (ev.key === 'Escape') { close(); input.blur(); } });
  form.addEventListener('submit', async ev => {
    ev.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    out.hidden = false;
    out.innerHTML = '<div class="gs-msg">Buscando…</div>';
    try {
      const url = 'https://nominatim.openstreetmap.org/search?' + new URLSearchParams({
        q, format: 'jsonv2', limit: '5', 'accept-language': 'pt-BR',
      });
      results = await fetchJSON(url);
    } catch (e) {
      out.innerHTML = '<div class="gs-msg">Não foi possível buscar agora. Tente de novo.</div>';
      return;
    }
    if (!results.length) { out.innerHTML = '<div class="gs-msg">Nenhum resultado.</div>'; return; }
    out.innerHTML = results.map((r, i) => {
      const [first, ...rest] = r.display_name.split(', ');
      return `<button type="button" data-i="${i}">${esc(first)}<small>${esc(rest.join(', '))}</small></button>`;
    }).join('');
  });
  out.addEventListener('click', ev => {
    const b = ev.target.closest('button[data-i]'); if (!b) return;
    const r = results[+b.dataset.i];
    close();
    input.value = r.display_name.split(', ').slice(0, 3).join(', ');
    clear.hidden = false;
    goToPlace(r);
  });
}
function goToPlace(r) {
  searchPin = { lat: +r.lat, lon: +r.lon };
  // enquadra a caixa do resultado (sul, norte, oeste, leste), com zoom máximo de nível de rua
  const [s, n, w, e] = r.boundingbox.map(Number);
  const [x0, y0] = projection([w, n]), [x1, y1] = projection([e, s]);
  const availW = W - (state.selected != null ? 440 : 0), pad = 80;
  const k = Math.max(0.06, Math.min(2500, (availW - 2 * pad) / Math.max(x1 - x0, 1e-6), (H - 2 * pad) / Math.max(y1 - y0, 1e-6)));
  const [cx, cy] = projection([searchPin.lon, searchPin.lat]);
  d3.select(canvas).transition().duration(650)
    .call(zoom.transform, d3.zoomIdentity.translate(availW / 2 - cx * k, H / 2 - cy * k).scale(k));
}

// ------------------------------------------------------------------ painel
const panelState = { tab: 1, parties: null, statuses: new Set(STATUS_ORDER), shown: 60, ctx: null, query: '', list: null };
// busca por nome sem acentos nem maiúsculas
const fold = s => String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

async function loadCand(scope) {
  if (!cand[scope]) cand[scope] = await fetchJSON(`data/cand/${scope}.json`);
  return cand[scope];
}
const sdCache = new Map();
async function loadLocalDetail(mun) {
  if (!sdCache.has(mun)) sdCache.set(mun, fetchJSON(`data/sd/${mun}.json`));
  return sdCache.get(mun);
}
async function loadDetail(id) {
  if (!detailCache.has(id)) detailCache.set(id, fetchJSON(`data/d/${id}.json`));
  return detailCache.get(id);
}

function closePanel() {
  state.selected = null;
  $('#panel').hidden = true;
  document.body.classList.remove('panel-open');
  drawOverlay();
}

async function openPanel(id) {
  state.selected = id;
  $('#panel').hidden = false;
  document.body.classList.add('panel-open');
  drawOverlay();
  const body = $('#panel-body');
  body.innerHTML = '<div class="empty">Carregando…</div>';
  let pc;   // contexto do painel
  try {
   if (typeof id === 'string' && id[0] === 'x') {
    const b = extCities.get(id);
    await loadCand('br');
    const map = {};
    for (const [sq, c] of Object.entries(cand.br)) map[c[1]] = sq;
    $('#panel-sub').textContent = `Exterior · ${titleCase(b.c.city)}`;
    $('#panel-title').textContent = titleCase(b.c.n);
    const v = Object.entries(b.c.v).filter(([n]) => map[n]).map(([n, vv]) => [map[n], vv]).sort((a, c) => c[1] - a[1]);
    const byZone = {};
    for (const [z, sec] of b.c.s) (byZone[z] = byZone[z] || []).push(sec);
    const secTxt = Object.entries(byZone).map(([z, ss]) => `Zona ${z}: ${ss.length > 1 ? 'seções' : 'seção'} ${ss.join(', ')}`).join(' · ');
    pc = { id, kind: 'local', uf: 'zz', detail: { c: { 1: { t: b.c.t, v } } }, tabs: [1],
      muns: secTxt + (b.c.aprox ? ' · posição aproximada (centro da cidade)' : '') };
   } else if (typeof id === 'number') {
    const inf = locais.info(id);
    const [sd] = await Promise.all([loadLocalDetail(inf.mun), loadCand('br'), loadCand(inf.uf)]);
    const d = sd[String(inf.idx)] || { s: [], c: {} };
    $('#panel-sub').textContent = `${titleCase(inf.munName)} (${inf.uf.toUpperCase()}) · Local de votação`;
    $('#panel-title').textContent = titleCase(inf.name || 'Local de votação');
    // número do candidato -> sq
    const byNum = (scope, cg) => {
      const m = {}; for (const [sq, c] of Object.entries(cand[scope])) if (c[4] === cg) m[c[1]] = sq; return m;
    };
    const c = {};
    for (const [cg, [t, v]] of Object.entries(d.c)) {
      const map = byNum(cg === '1' ? 'br' : inf.uf, +cg);
      c[cg] = { t, v: Object.entries(v).filter(([n]) => map[n]).map(([n, vv]) => [map[n], vv]).sort((a, b) => b[1] - a[1]) };
    }
    const byZone = {};
    for (const [z, sec] of d.s) (byZone[z] = byZone[z] || []).push(sec);
    const secTxt = Object.entries(byZone).map(([z, ss]) => `Zona ${z}: ${ss.length > 1 ? 'seções' : 'seção'} ${ss.join(', ')}`).join(' · ');
    pc = { id, kind: 'local', uf: inf.uf, detail: { c }, tabs: [1, 3, 5], muns: secTxt };
   } else {
    const e = S.el[id];
    const detail = await loadDetail(id);
    const uf = id === 'br' ? null : e.uf;
    await Promise.all([loadCand('br'), uf && uf !== 'zz' ? loadCand(uf) : null,
      id === 'br' ? Promise.all(Object.keys(S.uf).filter(u => u !== 'zz').map(loadCand)) : null]);
    const kind = id === 'br' ? 'pais' : id === 'zz' ? 'exterior' : id.length === 2 ? 'estado' : e.muns ? 'zona' : 'municipio';
    $('#panel-sub').textContent = kind === 'pais' ? 'País' : kind === 'exterior' ? 'Votos no exterior'
      : kind === 'estado' ? 'Estado' : kind === 'zona' ? `Zona eleitoral · ${S.uf[uf]}` : `Município · ${uf.toUpperCase()}`;
    $('#panel-title').textContent = kind === 'pais' ? 'Brasil' : kind === 'exterior' ? 'Exterior'
      : kind === 'estado' ? S.uf[id] : kind === 'zona' ? e.n : titleCase(e.n);
    const tabs = kind === 'pais' ? [1, 3, 5, 6] : kind === 'exterior' ? [1] : [1, 3, 5, 6, 7];
    pc = { id, kind, uf, detail, tabs, muns: kind === 'zona' ? zoneMuns(e, 12) : null };
   }
  } catch (err) {
    body.innerHTML = `<div class="empty">Não foi possível carregar os dados (${esc(err.message)}).</div>`;
    return;
  }
  if (state.selected !== id) return;
  panelState.ctx = pc;
  if (!pc.tabs.includes(panelState.tab)) panelState.tab = 1;
  panelState.parties = null;
  panelState.shown = 60;
  panelState.query = '';
  renderPanel();
}

function cargoKey(pc, tab) {
  // Distrito Federal: deputado distrital (cargo 8) no lugar de estadual
  if (tab === 7 && pc.detail.c['8']) return '8';
  return String(tab);
}
function candInfo(pc, sq, cargo, ufHint) {
  const scope = cargo === 1 ? 'br' : (ufHint || pc.uf);
  return (cand[scope] || {})[sq];
}

function renderPanel() {
  const pc = panelState.ctx;
  const body = $('#panel-body');
  const key = cargoKey(pc, panelState.tab);
  const cg = pc.detail.c[key] || {};
  const tot = cg.t || (pc.detail.c['1'] || {}).t;
  const totCargo = cg.t ? (CARGOS.find(c => c.id === panelState.tab) || {}).nome : 'Presidente';
  let html = '';
  if (pc.muns) html += `<div class="count" style="margin-top:-4px">${esc(pc.muns)}</div>`;
  if (tot) html += votacaoCard(tot, totCargo) + eleitoradoCard(tot);
  html += `<div class="tabs">${CARGOS.map(c => {
    const ok = pc.tabs.includes(c.id);
    const label = c.id === 7 && pc.detail.c['8'] ? 'Dep. Distrital' : c.nome;
    return `<button data-tab="${c.id}" class="${c.id === panelState.tab ? 'active' : ''}" ${ok ? '' : 'disabled'}>${label}</button>`;
  }).join('')}</div>`;

  // lista de candidatos
  const list = (cg.v || []).map(r => {
    const sq = r[0], votes = r[1];
    const ufHint = cg.list ? r[3] : null;
    const info = candInfo(pc, sq, panelState.tab === 7 && key === '8' ? 8 : panelState.tab, ufHint);
    // mesma base do TSE: válidos + anulados sub judice (t[5])
    const base = cg.t ? cg.t[2] + (cg.t[5] || 0) : 0;
    const pct = cg.list ? r[2] / 100 : (base ? votes / base : 0);
    return { sq, votes, pct, info, uf: ufHint || (panelState.tab === 1 ? 'br' : pc.uf) };
  }).filter(c => c.info);
  // na visão país, deputados federais (de UFs diferentes) são ordenados por votos; o resto, por %
  const byVotes = pc.kind === 'pais' && panelState.tab === 6;
  list.sort(byVotes ? (a, b) => b.votes - a.votes : (a, b) => b.pct - a.pct || b.votes - a.votes);

  const partyVotes = new Map();
  for (const c of list) partyVotes.set(c.info[2], (partyVotes.get(c.info[2]) || 0) + c.votes);
  const parties = [...partyVotes.entries()].sort((a, b) => b[1] - a[1]).map(([p]) => p);
  if (!panelState.parties) panelState.parties = new Set(parties);
  const presentStatus = STATUS_ORDER.filter(s => list.some(c => c.info[3] === s));

  html += `<div class="filters">
    <div class="fl"><span>Partido</span><span><button data-act="pall">todos</button> · <button data-act="pnone">nenhum</button></span></div>
    <div class="chips ${parties.length > 12 ? 'collapsed' : ''}" id="party-chips">${parties.map(p =>
      `<button class="chip ${panelState.parties.has(p) ? 'on' : ''}" data-party="${esc(p)}"><i style="background:${partyColor(p)}"></i>${esc(p)}</button>`).join('')}</div>
    ${parties.length > 12 ? '<button class="more-chips" data-act="pmore">mostrar todos os partidos</button>' : ''}
    <div class="fl"><span>Situação</span></div>
    <div class="chips">${presentStatus.map(s =>
      `<button class="chip ${panelState.statuses.has(s) ? 'on' : ''}" data-status="${s}"><i style="background:var(--st-${s})"></i>${STATUS[s]}</button>`).join('')}</div>
  </div>`;

  html += `<div class="search"><input type="search" id="cand-search" placeholder="Buscar candidato por nome ou número" value="${esc(panelState.query)}" autocomplete="off"></div>`;
  html += '<div id="cand-list"></div>';
  panelState.list = list;

  const scroll = body.scrollTop;
  body.innerHTML = html;
  renderCandList();
  body.scrollTop = scroll;
}

// só a lista (contagem + candidatos), para a busca não perder o foco ao digitar
function renderCandList() {
  const pc = panelState.ctx, list = panelState.list || [];
  const q = fold(panelState.query.trim());
  const filtered = list.filter(c => panelState.parties.has(c.info[2]) && panelState.statuses.has(c.info[3])
    && (!q || fold(c.info[0]).includes(q) || fold(c.info[5] || '').includes(q) || String(c.info[1]).startsWith(q)));
  const titleExtra = pc.kind === 'pais' && panelState.tab !== 1 ? ' eleitos ou no 2º turno, por UF' : '';
  let html = `<div class="count">${fmtInt.format(filtered.length)} de ${fmtInt.format(list.length)} candidatos${titleExtra}</div>`;
  if (!filtered.length) html += `<div class="empty">${q ? 'Nenhum candidato encontrado.' : 'Nenhum candidato com os filtros atuais.'}</div>`;
  html += filtered.slice(0, panelState.shown).map(c => candCard(c, pc)).join('');
  if (filtered.length > panelState.shown) html += `<button class="show-more" data-act="more">Mostrar mais (${fmtInt.format(filtered.length - panelState.shown)} restantes)</button>`;
  $('#cand-list').innerHTML = html;
}

function votacaoCard(t, cargoNome) {
  const [, comp, val, bra, nul] = t, sj = t[5] || 0;
  const total = comp || (val + sj + bra + nul);
  const p = x => total ? x / total : 0;
  return `<div class="card"><h2>Votação${cargoNome ? ` · ${esc(cargoNome)}` : ''}</h2>
    <div class="stack"><i style="width:${p(val) * 100}%;background:var(--valid)"></i><i style="width:${p(sj) * 100}%;background:var(--annul-sj)"></i><i style="width:${p(bra) * 100}%;background:var(--blank)"></i><i style="width:${p(nul) * 100}%;background:var(--null)"></i></div>
    <div class="big-num"><b>${fmtInt.format(total)}</b> Votos</div>
    <div class="row"><span>Nominais e de legenda</span><span class="pct">${fmtPct(p(val + sj))}</span></div>
    <div class="row sub"><span class="lbl"><span class="sq" style="background:var(--valid)"></span>Válidos</span><span>${fmtInt.format(val)}</span></div>
    ${sj ? `<div class="row sub"><span class="lbl"><span class="sq" style="background:var(--annul-sj)"></span>Anulados sub judice</span><span>${fmtInt.format(sj)}</span></div>` : ''}
    <div class="row"><span class="lbl"><span class="sq" style="background:var(--blank)"></span><span class="two">${fmtInt.format(bra)}<small>Em branco</small></span></span><span class="pct">${fmtPct(p(bra))}</span></div>
    <div class="row"><span class="lbl"><span class="sq" style="background:var(--null)"></span><span class="two">${fmtInt.format(nul)}<small>Nulos</small></span></span><span class="pct">${fmtPct(p(nul))}</span></div>
  </div>`;
}
function eleitoradoCard(t) {
  const [apt, comp] = t;
  const ab = Math.max(0, apt - comp);
  const pc = apt ? comp / apt : 0;
  return `<div class="card">
    <div class="row"><span>Eleitorado apto</span><b>${fmtInt.format(apt)}</b></div>
    <div class="abst"><div class="labels"><span>Comparecimento<b>${fmtInt.format(comp)}</b></span><span style="text-align:right">Abstenção<b>${fmtInt.format(ab)}</b></span></div>
    <div class="bar"><span class="c" style="width:${pc * 100}%">${pc > 0.15 ? fmtPct(pc) : ''}</span><span class="a" style="width:${(1 - pc) * 100}%">${1 - pc > 0.12 ? fmtPct(1 - pc) : ''}</span></div></div>
  </div>`;
}
function photoUrl(sq, cargo, uf) {
  const ele = cargo === 1 ? 6257 : 6259;
  const scope = cargo === 1 ? 'br' : uf;
  return `https://resultados.tse.jus.br/oficial/ele2026/${ele}/fotos/${scope}/${sq}.jpeg`;
}
function candCard(c, pc) {
  const [nome, num, partido, st, cargo] = c.info;
  const col = { E: '#3fb950', 2: '#e3b341', N: '#6e7681', S: '#58a6ff', A: '#f85149' }[st];
  const R = 25, C = 2 * Math.PI * R;
  const ini = nome.split(/\s+/).slice(0, 2).map(w => w[0]).join('');
  return `<div class="cand">
    <div class="ring"><svg viewBox="0 0 56 56"><circle cx="28" cy="28" r="${R}" fill="none" stroke="var(--surface-3)" stroke-width="3"/>
      <circle cx="28" cy="28" r="${R}" fill="none" stroke="${col}" stroke-width="3" stroke-dasharray="${C * Math.min(1, c.pct)} ${C}" stroke-linecap="round"/></svg>
      <img loading="lazy" src="${photoUrl(c.sq, cargo, c.uf)}" alt="" onerror="this.outerHTML='<span class=&quot;ini&quot;>${esc(ini)}</span>'"></div>
    <div class="info">
      <div class="party">${esc(partido)} – ${esc(num)}${pc.kind === 'pais' && panelState.tab !== 1 ? `<span class="uf-tag">${c.uf.toUpperCase()}</span>` : ''}</div>
      <div class="name" title="${esc(c.info[5] || nome)}">${esc(nome)}</div>
      <span class="pill ${st}">${STATUS[st]}</span>
    </div>
    <div class="nums"><div class="p">${fmtPct(c.pct)}</div><div class="v">${fmtInt.format(c.votes)} votos</div></div>
  </div>`;
}

$('#panel-body').addEventListener('input', ev => {
  if (ev.target.id !== 'cand-search') return;
  panelState.query = ev.target.value;
  panelState.shown = 60;
  renderCandList();
});
$('#panel-body').addEventListener('click', ev => {
  const b = ev.target.closest('button'); if (!b) return;
  if (b.dataset.tab) { panelState.tab = +b.dataset.tab; panelState.parties = null; panelState.shown = 60; renderPanel(); $('#panel-body').scrollTop = 0; return; }
  if (b.dataset.party) { const s = panelState.parties; s.has(b.dataset.party) ? s.delete(b.dataset.party) : s.add(b.dataset.party); panelState.shown = 60; renderPanel(); return; }
  if (b.dataset.status) { const s = panelState.statuses; s.has(b.dataset.status) ? s.delete(b.dataset.status) : s.add(b.dataset.status); panelState.shown = 60; renderPanel(); return; }
  const act = b.dataset.act;
  if (act === 'more') { panelState.shown += 100; renderCandList(); }
  if (act === 'pall') { panelState.parties = null; renderPanel(); }
  if (act === 'pnone') { panelState.parties = new Set(); renderPanel(); }
  if (act === 'pmore') { $('#party-chips').classList.remove('collapsed'); b.remove(); }
});

// gancho para testes automatizados: centraliza o mapa em [lon, lat] com zoom k
window.__mapaT = () => state.transform;
window.__mapa = {
  zoomToMap(x, y, k) {
    d3.select(canvas).call(zoom.transform, d3.zoomIdentity.translate(W / 2 - x * k, H / 2 - y * k).scale(k));
  },
  extCityScreen(i) {
    const b = [...extCities.values()][i], t = state.transform;  // ponto i do exterior
    return [b.x * t.k + t.x, b.y * t.k + t.y];
  },
  localScreen(lon, lat) {
    const [x, y] = projection([lon, lat]);
    const k = locais.nearest(x, y, 5), t = state.transform;
    return [locais.X[k] * t.k + t.x, locais.Y[k] * t.k + t.y];
  },
  redraw() { draw(); return lastDrawMs; },
  zoomTo(lon, lat, k) {
    const [x, y] = projection([lon, lat]);
    d3.select(canvas).call(zoom.transform, d3.zoomIdentity.translate(W / 2 - x * k, H / 2 - y * k).scale(k));
  },
};

init().catch(err => {
  $('#loading-text').textContent = 'Erro ao carregar: ' + err.message;
  console.error(err);
});
})();
