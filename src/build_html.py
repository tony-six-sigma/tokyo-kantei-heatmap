"""Build the interactive Tokyo map dashboard HTML.

Reads data/merged.json (Kantei rows + OSM coords) and writes kantei.html
to the repo root. The output is a single self-contained HTML file with
embedded data — no runtime data fetching needed.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser(description="Build the Kantei heatmap HTML.")
ap.add_argument("--public", action="store_true",
                help="ignore data/picks.json (use for the public deploy copy)")
ap.add_argument("--out", type=Path, default=ROOT / "kantei.html", help="output path")
args = ap.parse_args()

# Load merged dataset
with (ROOT / "data" / "merged.json").open(encoding="utf-8") as f:
    rows = json.load(f)

# Optional local-only annotation overlay. If data/picks.json exists, render
# orange rings on top of the heatmap. The file is gitignored — picks stay
# local. See data/picks.example.json for the schema.
picks_path = ROOT / "data" / "picks.json"

# Basemap: CARTO Voyager (the original look) when a key is available, else keyless 地理院タイル.
# CARTO keys are free by email (carto.com/basemaps) and end up in the page's tile URLs anyway;
# data/carto_key.txt is gitignored so the key isn't committed.
key_path = ROOT / "data" / "carto_key.txt"
carto_key = key_path.read_text(encoding="utf-8").strip() if key_path.exists() else ""
picks = json.loads(picks_path.read_text(encoding="utf-8")) if picks_path.exists() and not args.public else []

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

# Optional hazard layer: Tokyo 地域危険度 ranks on 町丁目 polygons (src/fetch_hazards.py).
# Each station inside a 町丁目 gets its building-collapse / fire / overall ranks.
risk_path = ROOT / "data" / "tokyo_risk.json"
towns = json.loads(risk_path.read_text(encoding="utf-8"))["towns"] if risk_path.exists() else []


def decode(enc):
    pts, x, y = [], 0, 0
    for i in range(0, len(enc), 2):
        x += enc[i]
        y += enc[i + 1]
        pts.append((x / 1e5, y / 1e5))
    return pts


def inside(lon, lat, rings):  # even-odd rule across all rings, same as the canvas fill
    c = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                c = not c
    return c


boxes = []
for t in towns:
    rings = [decode(e) for e in t[4]]
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    boxes.append((min(xs), min(ys), max(xs), max(ys), rings, t))
for r in located:
    for x0, y0, x1, y1, rings, t in boxes:
        if x0 <= r["lon"] <= x1 and y0 <= r["lat"] <= y1 and inside(r["lon"], r["lat"], rings):
            r["town"], r["r_col"], r["r_fire"], r["r_tot"] = t[0], t[1], t[2], t[3]
            break
print(f"Tokyo risk: {len(towns)} 町丁目, {sum(1 for r in located if 'town' in r)} stations tagged")

# Optional rent layer (src/fetch_rents.py): SUUMO マンション 1R asking rent now vs ~1 year ago.
# gap = rent growth minus price growth; positive means rents are outpacing prices. Only computed where
# Kantei's price vintage is late 2025 or newer, so both changes cover roughly the same year.
rents_path = ROOT / "data" / "station_rents.json"
rents = json.loads(rents_path.read_text(encoding="utf-8")) if rents_path.exists() else {"meta": {}, "stations": {}}
for r in located:
    v = rents["stations"].get(f'{r["line"]}|{r["station"]}')
    if v:
        r["rent"], r["rent_then"], r["rent_then_date"], r["rent_chg"] = v
        if v[3] is not None and r.get("yoy_1") is not None and (r.get("vintage") or "") >= "2025-10":
            r["gap"] = round(v[3] - r["yoy_1"], 1)
rent_date = rents["meta"].get("scraped", "")
print(f"Rents: {sum(1 for r in located if 'rent' in r)} stations, {sum(1 for r in located if 'gap' in r)} with rent vs price gap")

# Embed data as JSON in HTML
data_json = json.dumps(located, ensure_ascii=False, separators=(',', ':'))
towns_json = json.dumps(towns, ensure_ascii=False, separators=(',', ':'))
picks_json = json.dumps(picks, ensure_ascii=False, separators=(',', ':'))
n_lines = len({r["line"] for r in located})

if carto_key:
    basemap_js = f"""// Init map (CARTO Voyager; CARTO requires a key since 2026, keyless tiles are watermarked)
const map = L.map('map', {{ preferCanvas: true, maxZoom: 19 }}).setView([35.685, 139.71], 11);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png?key={carto_key}', {{
  attribution: '© OpenStreetMap contributors © CARTO',
  subdomains: 'abcd', maxZoom: 19
}}).addTo(map);"""
else:
    basemap_js = """// Init map. Basemap: 国土地理院 淡色地図, keyless (credit only, no application for real-time use:
// https://maps.gsi.go.jp/development/ichiran.html). Zoom 9-18 stays in the range where the
// 地理院タイル credit alone is enough. Add data/carto_key.txt to switch to CARTO Voyager.
const map = L.map('map', { preferCanvas: true, minZoom: 9, maxZoom: 18 }).setView([35.685, 139.71], 11);
L.tileLayer('https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png', {
  attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">地理院タイル</a> (国土地理院)',
  minZoom: 9, maxZoom: 18
}).addTo(map);"""

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
  .controls.hazards {{ background: #fff; padding-top: 8px; padding-bottom: 8px; }}
  .controls input[type=checkbox], .controls input[type=range] {{ padding: 0; border: none; vertical-align: middle; }}
  .controls.hazards label {{ font-weight: 500; cursor: pointer; }}
  .hz-legend {{ line-height: 1.5; max-width: 230px; }}
  .hz-legend .sq {{ display: inline-block; width: 14px; height: 12px; vertical-align: middle; margin-right: 6px;
                     border: 1px solid rgba(0,0,0,0.15); }}
  .hz-legend .bar {{ height: 10px; margin: 3px 0 1px; border: 1px solid rgba(0,0,0,0.15);
                      background: linear-gradient(to right, #fbe685 0%, #ffe601 10%, #ffdd00 12%, #ff9900 35%,
                      #ff8c00 38%, #ff4100 58%, #ff2800 60%, #c50951 82%, #b40068 84%, #b40068 100%); }}
  .hz-legend .ticks {{ display: flex; justify-content: space-between; font-size: 10px; color: #555; }}
  .hz-legend + .hz-legend {{ margin-top: 6px; }}
</style>
</head>
<body>

<header>
  <h1>Tokyo Capital-Gains Heatmap</h1>
  <div class="sub">Kantei 沿線・駅別 data — {len(located)} stations across {n_lines} Tokyo-area lines (updated 2026-08).
    Color = 1-yr YoY ¥/坪 change. Size = sub-¥100M affordability. Per-station data vintage in popup/table — lines refresh on a ~2yr rotation.
    Rent metrics: SUUMO マンション ワンルーム asking rent ({rent_date}) vs an archived copy from about a year earlier; positive "rent − price" means rents are outpacing prices (shown only where Kantei's price data is late-2025 or newer, so both cover about the same year).
    Hazard overlays: MLIT flood maps, J-SHIS earthquake shaking probability, Tokyo 地域危険度 (第9回) ranks; click the map for a 町丁目's ranks.</div>
</header>

<div class="controls">
  <span><label>Color metric:</label>
    <select id="metric">
      <option value="yoy_1">1-yr YoY %</option>
      <option value="yoy_2">2-yr cumulative %</option>
      <option value="cagr_2">2-yr CAGR %</option>
      <option value="rent_chg">Rent change %/yr (SUUMO 1R)</option>
      <option value="gap">Rent growth − price growth (pts)</option>
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

<div class="controls hazards">
  <span><label>Hazards:</label></span>
  <span><label><input type="checkbox" id="hzFlood"> Flood</label>
    <select id="hzFloodType">
      <option value="river">River, max-scale (洪水)</option>
      <option value="rain">Rainwater (内水)</option>
      <option value="surge">Storm surge (高潮)</option>
    </select>
  </span>
  <span><label><input type="checkbox" id="hzQuake"> Earthquake</label>
    <select id="hzQuakeType">
      <option value="collapse">Building collapse rank (Tokyo)</option>
      <option value="total">Overall risk rank (Tokyo)</option>
      <option value="shake">Shaking ≥ 震度6弱 in 30 yrs (J-SHIS)</option>
    </select>
  </span>
  <span><label><input type="checkbox" id="hzFire"> Fire spread rank (Tokyo)</label></span>
  <span><label for="hzOpacity">Opacity</label> <input type="range" id="hzOpacity" min="20" max="90" value="55" style="width:110px"></span>
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
        <th data-sort="rent" title="SUUMO マンション ワンルーム asking rent, 万円/month">Rent 1R</th>
        <th data-sort="rent_chg" title="Rent change, % per year">Rent %/yr</th>
        <th data-sort="gap" title="Rent growth minus 1-yr price growth, percentage points">Rent−price</th>
        <th data-sort="r_col" title="Tokyo 地域危険度 building collapse rank, 1 low to 5 high">倒壊</th>
        <th data-sort="r_fire" title="Tokyo 地域危険度 fire spread rank, 1 low to 5 high">火災</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<script>
const DATA = {data_json};
const PICKS = {picks_json};
const TOWNS = {towns_json};  // [label, collapse rank, fire rank, overall rank, [delta-encoded rings]]

// Color scales (divergent). Rent moves less than prices, so it gets tighter bands.
const PALETTE = ["#67000d", "#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#91cf60", "#1a9850", "#006837"];
const SCALES = {{
  price:    {{ cuts: [-15, -7, -2, 2, 8, 18, 30], unit: '%' }},
  rent_chg: {{ cuts: [-6, -3, -1, 1, 3, 6, 10], unit: '%' }},
  gap:      {{ cuts: [-25, -15, -8, -2, 2, 6, 12], unit: ' pts' }},
}};
const LEGEND_TITLES = {{ yoy_1: '1-yr YoY ¥/坪', yoy_2: '2-yr cumulative ¥/坪', cagr_2: '2-yr CAGR ¥/坪',
  rent_chg: 'Rent change %/yr (1R)', gap: 'Rent growth − price growth' }};
const scaleFor = m => SCALES[m] || SCALES.price;
function colorFor(v, metric) {{
  if (v == null || isNaN(v)) return "#999";
  const cuts = scaleFor(metric).cuts;
  for (let i = 0; i < cuts.length; i++) if (v <= cuts[i]) return PALETTE[i];
  return PALETTE[cuts.length];
}}

// Marker radius by affordability
function radiusFor(p_now) {{
  if (p_now <= 250) return 11;
  if (p_now <= 350) return 9;
  if (p_now <= 500) return 7;
  if (p_now <= 700) return 5;
  return 4;
}}

{basemap_js}

// Legend (rebuilt when the color metric changes)
const legend = L.control({{ position: 'bottomright' }});
legend.onAdd = function () {{
  const div = L.DomUtil.create('div', 'legend');
  div.id = 'legend';
  return div;
}};
legend.addTo(map);
function renderLegend(metric) {{
  const {{ cuts, unit }} = scaleFor(metric), s = v => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v) + unit;
  const rows = [`≥ ${{s(cuts[6])}}`];
  for (let i = 6; i > 0; i--) rows.push(`${{s(cuts[i - 1])}} to ${{s(cuts[i])}}`);
  rows.push(`≤ ${{s(cuts[0])}}`);
  document.getElementById('legend').innerHTML = `<div><b>${{LEGEND_TITLES[metric]}}</b></div>` +
    rows.map((t, i) => `<div><span class="swatch" style="background:${{PALETTE[7 - i]}}"></span>${{t}}</div>`).join('') +
    `<div><span class="swatch" style="background:#999"></span>no data</div>`;
}}

// Hazard overlays. Raster tiles sit above the basemap, Tokyo rank polygons above the tiles,
// station markers above both. Rank polygons are non-interactive so clicks reach the map.
map.createPane('hazardTiles').style.zIndex = 380;
map.createPane('riskPolys').style.zIndex = 390;
map.getPane('riskPolys').style.pointerEvents = 'none';
const $ = id => document.getElementById(id);
const hzOpacity = () => $('hzOpacity').value / 100;
const MLIT = '<a href="https://disaportal.gsi.go.jp/" target="_blank" rel="noopener">ハザードマップポータルサイト</a> (国土交通省)';
const JSHIS_ATTR = '<a href="https://www.j-shis.bosai.go.jp/" target="_blank" rel="noopener">J-SHIS</a> (防災科研, 2024年版)';
const TOKYO_ATTR = '地域危険度 第9回: <a href="https://www.toshiseibi.metro.tokyo.lg.jp/" target="_blank" rel="noopener">東京都都市整備局</a> (CC BY) · 境界: <a href="https://www.e-stat.go.jp/" target="_blank" rel="noopener">e-Stat</a>';
const FLOOD = {{ river: '01_flood_l2_shinsuishin_data', rain: '02_naisui_data', surge: '03_hightide_l2_shinsuishin_data' }};
const RANK_COLORS = ['#ffffcc', '#fed976', '#fd8d3c', '#e31a1c', '#800026'];
const riskRenderer = L.canvas({{ pane: 'riskPolys' }});
let floodLayer = null, quakeLayer = null, fireLayer = null, towns = null;

function decodeRing(e) {{
  const out = []; let x = 0, y = 0;
  for (let i = 0; i < e.length; i += 2) {{ x += e[i]; y += e[i + 1]; out.push([y / 1e5, x / 1e5]); }}
  return out;
}}
function getTowns() {{
  if (!towns) towns = TOWNS.map(t => {{
    const rings = t[4].map(decodeRing), lats = rings.flat().map(p => p[0]), lons = rings.flat().map(p => p[1]);
    return {{ label: t[0], r: [t[1], t[2], t[3]], rings,
             box: [Math.min(...lats), Math.min(...lons), Math.max(...lats), Math.max(...lons)] }};
  }});
  return towns;
}}
function floodTiles(type) {{
  return L.tileLayer(`https://disaportaldata.gsi.go.jp/raster/${{FLOOD[type]}}/{{z}}/{{x}}/{{y}}.png`,
    {{ pane: 'hazardTiles', opacity: hzOpacity(), maxNativeZoom: 17, maxZoom: 18, attribution: MLIT }});
}}
function shakeTiles() {{
  return L.tileLayer.wms('https://www.j-shis.bosai.go.jp/map/wms/pshm/Y2024?', {{
    layers: 'P-Y2024-MAP-AVR-TTL_MTTL-T30_I55_PS', format: 'image/png', transparent: true, version: '1.3.0',
    pane: 'hazardTiles', opacity: hzOpacity(), attribution: JSHIS_ATTR }});
}}
function rankLayer(idx) {{  // 0 building collapse, 1 fire spread, 2 overall
  const g = L.layerGroup([], {{ attribution: TOKYO_ATTR }});
  getTowns().forEach(t => L.polygon(t.rings, {{
    renderer: riskRenderer, interactive: false, color: '#fff', weight: 0.3,
    fillColor: RANK_COLORS[t.r[idx] - 1], fillOpacity: hzOpacity() }}).addTo(g));
  return g;
}}
function swap(current, want, make) {{
  if (current && (!want || current._hz !== want)) {{ map.removeLayer(current); current = null; }}
  if (want && !current) {{ current = make(want); current._hz = want; current.addTo(map); }}
  return current;
}}
function syncHazards() {{
  floodLayer = swap(floodLayer, $('hzFlood').checked && $('hzFloodType').value, floodTiles);
  quakeLayer = swap(quakeLayer, $('hzQuake').checked && $('hzQuakeType').value,
    t => t === 'shake' ? shakeTiles() : rankLayer(t === 'collapse' ? 0 : 2));
  fireLayer = swap(fireLayer, $('hzFire').checked && 'fire', () => rankLayer(1));
  renderHazardLegend();
}}
function setOpacity() {{
  const op = hzOpacity();
  [floodLayer, quakeLayer, fireLayer].forEach(l => {{
    if (!l) return;
    if (l.setOpacity) l.setOpacity(op); else l.eachLayer(p => p.setStyle({{ fillOpacity: op }}));
  }});
}}
const tokyoRankOn = () => ($('hzQuake').checked && $('hzQuakeType').value !== 'shake') || $('hzFire').checked;

// One Tokyo rank layer at a time (they share the 町丁目 polygons). Picking a type turns its layer on.
$('hzFlood').addEventListener('change', syncHazards);
$('hzFloodType').addEventListener('change', () => {{ $('hzFlood').checked = true; syncHazards(); }});
['hzQuake', 'hzQuakeType'].forEach(id => $(id).addEventListener('change', () => {{
  if (id === 'hzQuakeType') $('hzQuake').checked = true;
  if ($('hzQuake').checked && $('hzQuakeType').value !== 'shake') $('hzFire').checked = false;
  syncHazards();
}}));
$('hzFire').addEventListener('change', () => {{
  if ($('hzFire').checked && $('hzQuakeType').value !== 'shake') $('hzQuake').checked = false;
  syncHazards();
}});
$('hzOpacity').addEventListener('input', setOpacity);

// Hazard legend (bottom-left), rebuilt for whichever layers are on
const hzLegend = L.control({{ position: 'bottomleft' }});
hzLegend.onAdd = () => {{ const d = L.DomUtil.create('div', 'legend'); d.id = 'hzLegend'; d.style.display = 'none'; return d; }};
hzLegend.addTo(map);
function renderHazardLegend() {{
  const parts = [], sq = c => `<span class="sq" style="background:${{c}}"></span>`;
  if (floodLayer) {{
    const t = {{ river: 'River flood depth (max scale)', rain: 'Rainwater flood depth (内水)', surge: 'Storm-surge depth (高潮)' }}[floodLayer._hz];
    parts.push(`<div class="hz-legend"><b>${{t}}</b><br>` +
      [['#dc7adc', '20m+'], ['#f285c9', '10–20m'], ['#ff9191', '5–10m'], ['#ffb7b7', '3–5m'], ['#ffd8c0', '0.5–3m'], ['#f7f5a9', 'under 0.5m']]
        .map(([c, l]) => `${{sq(c)}}${{l}}`).join('<br>') +
      `<div style="color:#777;font-size:10px">Lighter sub-shades mark the 0.3m and 1m bands. Rainwater maps exist only where cities published them.</div></div>`);
  }}
  if (quakeLayer && quakeLayer._hz === 'shake') {{
    parts.push(`<div class="hz-legend"><b>Chance of 震度6弱+ shaking within 30 yrs</b><div class="bar"></div>
      <div class="ticks"><span>0</span><span>0.1</span><span>3</span><span>6</span><span>26</span><span>100%</span></div></div>`);
  }}
  const rankOn = [quakeLayer && quakeLayer._hz !== 'shake' && (quakeLayer._hz === 'collapse' ? 'Building collapse' : 'Overall'),
                  fireLayer && 'Fire spread'].filter(Boolean);
  if (rankOn.length) {{
    parts.push(`<div class="hz-legend"><b>${{rankOn.join(' / ')}} rank (Tokyo 町丁目)</b><br>` +
      RANK_COLORS.map((c, i) => `${{sq(c)}}${{i + 1}}${{i === 0 ? ' lowest' : i === 4 ? ' highest' : ''}}`).reverse().join('<br>') +
      `<div style="color:#777;font-size:10px">Relative within Tokyo; no data outside 東京都 or in 市街化調整区域.</div></div>`);
  }}
  const d = $('hzLegend'); d.innerHTML = parts.join(''); d.style.display = parts.length ? '' : 'none';
}}

// Click the map with a Tokyo rank layer on to see that 町丁目's ranks
const hzInfo = L.control({{ position: 'topright' }});
hzInfo.onAdd = () => {{ const d = L.DomUtil.create('div', 'legend'); d.id = 'hzInfo'; d.style.display = 'none'; return d; }};
hzInfo.addTo(map);
function townAt(lat, lon) {{
  return getTowns().find(t => lat >= t.box[0] && lon >= t.box[1] && lat <= t.box[2] && lon <= t.box[3] &&
    t.rings.reduce((c, ring) => {{
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {{
        const [yi, xi] = ring[i], [yj, xj] = ring[j];
        if ((yi > lat) !== (yj > lat) && lon < xi + (lat - yi) * (xj - xi) / (yj - yi)) c = !c;
      }}
      return c;
    }}, false));
}}
map.on('click', e => {{
  const d = $('hzInfo');
  if (!tokyoRankOn()) {{ d.style.display = 'none'; return; }}
  const t = townAt(e.latlng.lat, e.latlng.lng);
  d.innerHTML = t ? `<b>${{t.label}}</b><br>Building collapse ${{t.r[0]}}/5 · Fire ${{t.r[1]}}/5 · Overall ${{t.r[2]}}/5`
                  : 'No Tokyo 地域危険度 data here';
  d.style.display = '';
}});

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
    ${{r.rent ? `<hr style="margin:6px 0;border:none;border-top:1px solid #eee">
    <div style="color:#666;font-size:11px">Rent, SUUMO マンション ワンルーム (asking)</div>
    <div class="row"><span>Now ({rent_date})</span><b>¥${{r.rent}}万</b></div>
    ${{r.rent_then ? `<div class="row"><span>Then (${{r.rent_then_date}})</span><span>¥${{r.rent_then}}万</span></div>
    <div class="row"><span>Rent change</span><span class="${{r.rent_chg >= 0 ? 'pos' : 'neg'}}">${{fmt(r.rent_chg, 1, true)}}%/yr</span></div>
    <div class="row"><span>Rent − price growth</span><span class="${{r.gap >= 0 ? 'pos' : 'neg'}}">${{fmt(r.gap, 1, true)}} pts</span></div>` : ''}}` : ''}}
    ${{r.town ? `<hr style="margin:6px 0;border:none;border-top:1px solid #eee">
    <div style="color:#666;font-size:11px">Tokyo 地域危険度 · ${{r.town}} (1 low, 5 high)</div>
    <div class="row"><span>Building collapse</span><b>${{r.r_col}}/5</b></div>
    <div class="row"><span>Fire spread</span><b>${{r.r_fire}}/5</b></div>
    <div class="row"><span>Overall</span><b>${{r.r_tot}}/5</b></div>` : ''}}
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
      fillColor: colorFor(v, metric),
      color: '#000', weight: 0.5, fillOpacity: 0.85
    }}).bindTooltip(`<b>${{r.station}}</b> ${{fmt(v, 1, true)}}${{scaleFor(metric).unit}}`, {{ direction: 'top' }})
      .bindPopup(popup(r))
      .addTo(markerLayer);
  }});
  document.getElementById('counter').textContent = rows.length + ' stations';

  // Stats for the selected metric
  const vals = rows.map(r => r[metric]).filter(v => v != null);
  const up = vals.filter(v => v > 0).length;
  const down = vals.filter(v => v < 0).length;
  const median = vals.length ? [...vals].sort((a,b)=>a-b)[Math.floor(vals.length/2)] : 0;
  document.getElementById('stats').textContent =
    `${{rows.length}} stations matched · ${{LEGEND_TITLES[metric]}}: ${{up}} up / ${{down}} down · median ${{fmt(median, 1, true)}}${{scaleFor(metric).unit}}` +
    (vals.length < rows.length ? ` (${{rows.length - vals.length}} without data)` : '');
  renderLegend(metric);
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
      <td>${{r.rent ?? '—'}}</td>
      <td class="${{r.rent_chg == null ? '' : r.rent_chg >= 0 ? 'pos' : 'neg'}}">${{fmt(r.rent_chg, 1, true)}}</td>
      <td class="${{r.gap == null ? '' : r.gap >= 0 ? 'pos' : 'neg'}}">${{fmt(r.gap, 1, true)}}</td>
      <td>${{r.r_col ?? '—'}}</td>
      <td>${{r.r_fire ?? '—'}}</td>
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

out_path = args.out
out_path.write_text(html, encoding="utf-8")
print(f"Wrote {out_path} ({len(html)//1024} KB)")
