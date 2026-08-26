"""Build the interactive Tokyo map dashboard HTML.

Reads data/merged.json (Kantei rows + OSM coords) and writes kantei.html
to the repo root. The output is a single self-contained HTML file with
embedded data — no runtime data fetching needed.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load merged dataset
with (ROOT / "data" / "merged.json").open(encoding="utf-8") as f:
    rows = json.load(f)

# Optional local-only annotation overlay. If data/picks.json exists, render
# orange rings on top of the heatmap. The file is gitignored — picks stay
# local. See data/picks.example.json for the schema.
picks_path = ROOT / "data" / "picks.json"
picks = json.loads(picks_path.read_text(encoding="utf-8")) if picks_path.exists() else []

# Patch the 6 unmatched coords manually
manual_coords = {
    ("東京メトロ副都心線", "明治神宮前"): (35.6688, 139.7058),
    ("東京メトロ半蔵門線", "押上"): (35.7100, 139.8131),
    ("東京メトロ丸ノ内線①", "四ッ谷"): (35.6857, 139.7310),
    ("東京メトロ丸ノ内線②", "南阿佐ヶ谷"): (35.6970, 139.6361),
    ("京急本線②", "黄金町"): (35.4421, 139.6249),
    ("京急本線②", "上大岡"): (35.3963, 139.5906),
}
for r in rows:
    if r["lat"] is None:
        key = (r["line"], r["station"])
        if key in manual_coords:
            r["lat"], r["lon"] = manual_coords[key]

# Filter to located rows for the map
located = [r for r in rows if r["lat"] is not None]
print(f"Located: {len(located)}")

# Embed data as JSON in HTML
data_json = json.dumps(located, ensure_ascii=False, separators=(',', ':'))
picks_json = json.dumps(picks, ensure_ascii=False, separators=(',', ':'))
n_lines = len({r["line"] for r in located})

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tokyo Capital-Gains Heatmap — Kantei station data</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", sans-serif;
         margin: 0; background: #f5f5f5; color: #222; }}
  header {{ padding: 14px 22px 10px; background: #fff; border-bottom: 1px solid #ddd; }}
  h1 {{ margin: 0; font-size: 18px; font-weight: 600; }}
  .sub {{ color: #666; font-size: 12px; margin-top: 2px; }}
  .controls {{ padding: 12px 22px; background: #fafafa; border-bottom: 1px solid #ddd;
              display: flex; flex-wrap: wrap; gap: 14px 24px; align-items: center; font-size: 13px; }}
  .controls label {{ font-weight: 500; }}
  .controls select, .controls input {{ padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }}
  #map {{ height: 540px; }}
  .legend {{ background: #fff; padding: 10px 14px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,.2);
            font-size: 12px; line-height: 1.7; }}
  .legend .swatch {{ display: inline-block; width: 14px; height: 14px; vertical-align: middle;
                     margin-right: 6px; border-radius: 50%; border: 1px solid rgba(0,0,0,0.2); }}
  .leaflet-tooltip {{ font-size: 12px; padding: 6px 10px; }}
  .pop {{ font-size: 12px; min-width: 200px; }}
  .pop h3 {{ margin: 0 0 4px; font-size: 14px; }}
  .pop .row {{ display: flex; justify-content: space-between; gap: 12px; }}
  .pop .row b {{ font-weight: 600; }}
  .pop .pos {{ color: #1a7a35; font-weight: 600; }}
  .pop .neg {{ color: #c0392b; font-weight: 600; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 12.5px; }}
  th, td {{ padding: 6px 10px; text-align: right; border-bottom: 1px solid #eee; }}
  th {{ position: sticky; top: 0; background: #f0f0f0; cursor: pointer; user-select: none;
        font-weight: 600; text-align: right; z-index: 10; }}
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
  th.sort-asc::after {{ content: " ▲"; color: #888; font-size: 9px; }}
  th.sort-desc::after {{ content: " ▼"; color: #888; font-size: 9px; }}
  td.pos {{ color: #1a7a35; font-weight: 600; }}
  td.neg {{ color: #c0392b; font-weight: 600; }}
  tr:hover {{ background: #f8f8f8; }}
  .table-wrap {{ max-height: 420px; overflow-y: auto; background: #fff; border-top: 1px solid #ddd; }}
  .stats {{ padding: 8px 22px; background: #fff; font-size: 12px; color: #555; border-bottom: 1px solid #ddd; }}
  .pin-tony {{ stroke: #ff6b00; stroke-width: 3; }}
</style>
</head>
<body>

<header>
  <h1>Tokyo Capital-Gains Heatmap</h1>
  <div class="sub">Kantei 沿線・駅別 data — {len(located)} stations across {n_lines} Tokyo-area lines (updated 2026-08).
    Color = 1-yr YoY ¥/坪 change. Size = sub-¥100M affordability. Per-station data vintage in popup/table — lines refresh on a ~2yr rotation.</div>
</header>

<div class="controls">
  <span><label>Color metric:</label>
    <select id="metric">
      <option value="yoy_1">1-yr YoY %</option>
      <option value="yoy_2">2-yr cumulative %</option>
      <option value="cagr_2">2-yr CAGR %</option>
    </select>
  </span>
  <span><label>Affordability:</label>
    <select id="afford">
      <option value="all">All stations</option>
      <option value="60">60㎡ 2BR fits ¥100M (¥/坪 ≤ 551)</option>
      <option value="70">70㎡ 2BR fits ¥100M (¥/坪 ≤ 472)</option>
      <option value="80">80㎡ 2BR fits ¥100M (¥/坪 ≤ 413)</option>
    </select>
  </span>
  <span><label>Min growth (1yr%):</label>
    <input type="number" id="minGrowth" value="-100" step="5" style="width:60px"> %
  </span>
  <span><label>Line filter:</label>
    <select id="lineFilter"><option value="">All lines</option></select>
  </span>
  <span id="counter" style="color:#666"></span>
</div>

<div id="map"></div>

<div class="stats" id="stats"></div>

<div class="table-wrap">
  <table id="dataTable">
    <thead>
      <tr>
        <th data-sort="station">Station</th>
        <th data-sort="line">Line</th>
        <th data-sort="p_now">¥/坪 now</th>
        <th data-sort="yoy_1">1y %</th>
        <th data-sort="yoy_2">2y %</th>
        <th data-sort="cagr_2">2y CAGR</th>
        <th data-sort="max_sqm_100m">Max㎡ @¥100M</th>
        <th data-sort="avg_sqm">avg㎡</th>
        <th data-sort="avg_age">築年</th>
        <th data-sort="vintage">Data vintage</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<script>
const DATA = {data_json};
const PICKS = {picks_json};

// Color scale (divergent)
function colorFor(v) {{
  if (v == null || isNaN(v)) return "#999";
  if (v <= -15) return "#67000d";
  if (v <= -7)  return "#d73027";
  if (v <= -2)  return "#fc8d59";
  if (v <= 2)   return "#fee08b";
  if (v <= 8)   return "#d9ef8b";
  if (v <= 18)  return "#91cf60";
  if (v <= 30)  return "#1a9850";
  return "#006837";
}}

// Marker radius by affordability
function radiusFor(p_now) {{
  if (p_now <= 250) return 11;
  if (p_now <= 350) return 9;
  if (p_now <= 500) return 7;
  if (p_now <= 700) return 5;
  return 4;
}}

// Init map (CartoDB Voyager — works from file:// and any host, no Referer restriction)
const map = L.map('map', {{ preferCanvas: true }}).setView([35.685, 139.71], 11);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '© OpenStreetMap contributors © CARTO',
  subdomains: 'abcd', maxZoom: 19
}}).addTo(map);

// Legend
const legend = L.control({{ position: 'bottomright' }});
legend.onAdd = function () {{
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = '<div><b>1-yr YoY ¥/坪</b></div>' +
    '<div><span class="swatch" style="background:#006837"></span>≥ +30% (very hot)</div>' +
    '<div><span class="swatch" style="background:#1a9850"></span>+18% to +30%</div>' +
    '<div><span class="swatch" style="background:#91cf60"></span>+8% to +18%</div>' +
    '<div><span class="swatch" style="background:#d9ef8b"></span>+2% to +8%</div>' +
    '<div><span class="swatch" style="background:#fee08b"></span>−2% to +2% (flat)</div>' +
    '<div><span class="swatch" style="background:#fc8d59"></span>−7% to −2%</div>' +
    '<div><span class="swatch" style="background:#d73027"></span>−15% to −7%</div>' +
    '<div><span class="swatch" style="background:#67000d"></span>≤ −15% (rolling over)</div>';
  return div;
}};
legend.addTo(map);

// Markers layer
let markerLayer = L.layerGroup().addTo(map);

// Picks overlay (only renders if data/picks.json was present at build time)
PICKS.forEach(p => {{
  L.circleMarker([p.lat, p.lon], {{
    radius: 14, color: '#ff6b00', weight: 3, fillOpacity: 0,
    interactive: true
  }}).bindTooltip(p.label, {{ permanent: false, direction: 'top' }})
    .addTo(map);
}});

// Populate line filter
const allLines = [...new Set(DATA.map(r => r.line))].sort();
const lineSel = document.getElementById('lineFilter');
allLines.forEach(l => {{
  const o = document.createElement('option');
  o.value = l; o.textContent = l;
  lineSel.appendChild(o);
}});

// Filter and render
function fmt(v, dec=1, sign=false) {{
  if (v == null || isNaN(v)) return "—";
  return (sign && v > 0 ? "+" : "") + v.toFixed(dec);
}}

function popup(r) {{
  const c1 = r.yoy_1 >= 0 ? 'pos' : 'neg';
  const c2 = r.yoy_2 >= 0 ? 'pos' : 'neg';
  return `<div class="pop">
    <h3>${{r.station}}</h3>
    <div style="color:#666;margin-bottom:6px;font-size:11px">${{r.line}}</div>
    <div class="row"><span>¥/坪 (now)</span><b>¥${{r.p_now}}万</b></div>
    <div class="row"><span>1-yr YoY</span><span class="${{c1}}">${{fmt(r.yoy_1, 1, true)}}%</span></div>
    <div class="row"><span>2-yr cumulative</span><span class="${{c2}}">${{fmt(r.yoy_2, 1, true)}}%</span></div>
    <div class="row"><span>2-yr CAGR</span><span>${{fmt(r.cagr_2, 1, true)}}%</span></div>
    <hr style="margin:6px 0;border:none;border-top:1px solid #eee">
    <div class="row"><span>Max ㎡ at ¥100M</span><b>${{fmt(r.max_sqm_100m, 1)}}㎡</b></div>
    <div class="row"><span>avg unit ㎡</span>${{fmt(r.avg_sqm, 1)}}</div>
    <div class="row"><span>avg 築年</span>${{fmt(r.avg_age, 1)}} yr</div>
    <div class="row"><span>data vintage</span><span style="color:#666">${{r.vintage || '?'}}</span></div>
  </div>`;
}}

let sortKey = 'yoy_1';
let sortDir = -1;

function applyFilters() {{
  const metric = document.getElementById('metric').value;
  const afford = document.getElementById('afford').value;
  const minG = parseFloat(document.getElementById('minGrowth').value || -100);
  const line = document.getElementById('lineFilter').value;
  const tholds = {{ "60": 551, "70": 472, "80": 413 }};
  const tcap = tholds[afford];

  return DATA.filter(r => {{
    if (tcap && r.p_now > tcap) return false;
    if (r.yoy_1 != null && r.yoy_1 < minG) return false;
    if (line && r.line !== line) return false;
    return true;
  }});
}}

function renderMap(rows) {{
  markerLayer.clearLayers();
  const metric = document.getElementById('metric').value;
  rows.forEach(r => {{
    if (!r.lat) return;
    const v = r[metric];
    L.circleMarker([r.lat, r.lon], {{
      radius: radiusFor(r.p_now),
      fillColor: colorFor(v),
      color: '#000', weight: 0.5, fillOpacity: 0.85
    }}).bindTooltip(`<b>${{r.station}}</b> ${{fmt(v, 1, true)}}%`, {{ direction: 'top' }})
      .bindPopup(popup(r))
      .addTo(markerLayer);
  }});
  document.getElementById('counter').textContent = rows.length + ' stations';

  // Stats
  const yoy = rows.map(r => r.yoy_1).filter(v => v != null);
  const up = yoy.filter(v => v > 0).length;
  const down = yoy.filter(v => v < 0).length;
  const median = yoy.length ? [...yoy].sort((a,b)=>a-b)[Math.floor(yoy.length/2)] : 0;
  document.getElementById('stats').textContent =
    `${{rows.length}} stations matched · 1-yr YoY: ${{up}} up / ${{down}} down · median ${{fmt(median, 1, true)}}%`;
}}

function renderTable(rows) {{
  const sorted = [...rows].sort((a, b) => {{
    const av = a[sortKey], bv = b[sortKey];
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "string") return sortDir * av.localeCompare(bv);
    return sortDir * (av - bv);
  }});
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = sorted.slice(0, 600).map(r => {{
    const c1 = r.yoy_1 == null ? '' : (r.yoy_1 >= 0 ? 'pos' : 'neg');
    const c2 = r.yoy_2 == null ? '' : (r.yoy_2 >= 0 ? 'pos' : 'neg');
    const cc = r.cagr_2 == null ? '' : (r.cagr_2 >= 0 ? 'pos' : 'neg');
    return `<tr>
      <td>${{r.station}}</td>
      <td style="font-size:11px;color:#666">${{r.line}}</td>
      <td>${{r.p_now}}</td>
      <td class="${{c1}}">${{fmt(r.yoy_1, 1, true)}}</td>
      <td class="${{c2}}">${{fmt(r.yoy_2, 1, true)}}</td>
      <td class="${{cc}}">${{fmt(r.cagr_2, 1, true)}}</td>
      <td>${{fmt(r.max_sqm_100m, 0)}}</td>
      <td>${{fmt(r.avg_sqm, 1)}}</td>
      <td>${{fmt(r.avg_age, 1)}}</td>
      <td style="color:#666">${{r.vintage || '?'}}</td>
    </tr>`;
  }}).join('');

  // Update sort indicators
  document.querySelectorAll('th').forEach(th => {{
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === sortKey)
      th.classList.add(sortDir > 0 ? 'sort-asc' : 'sort-desc');
  }});
}}

function refresh() {{
  const rows = applyFilters();
  renderMap(rows);
  renderTable(rows);
}}

// Wire up controls
document.querySelectorAll('#metric, #afford, #minGrowth, #lineFilter').forEach(el =>
  el.addEventListener('change', refresh));
document.getElementById('minGrowth').addEventListener('input', refresh);

document.querySelectorAll('th[data-sort]').forEach(th => {{
  th.addEventListener('click', () => {{
    const k = th.dataset.sort;
    if (sortKey === k) sortDir = -sortDir;
    else {{ sortKey = k; sortDir = (k === 'station' || k === 'line') ? 1 : -1; }}
    renderTable(applyFilters());
  }});
}});

refresh();
</script>
</body>
</html>
"""

out_path = ROOT / "kantei.html"
out_path.write_text(html, encoding="utf-8")
print(f"Wrote {out_path} ({len(html)//1024} KB)")
