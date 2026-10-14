# tokyo-kantei-heatmap

Interactive Tokyo capital-gains heatmap built from Tokyo Kantei's
**沿線・駅別中古マンション平均坪単価** reports. Plots 584 stations across 61
Tokyo-area train lines, color-coded by 1-year YoY ¥/坪 change and sized by
sub-¥100M affordability — meant for spotting which areas are still going up
and which have rolled over. Each station row carries the publication vintage
of its line's Kantei report (shown in popup + table).

**Live deployment:** https://web-tony-six-sigmas-projects.vercel.app/kantei.html

![preview](kantei.html)

---

## What's in here

```
.
├── kantei.html               # Built dashboard (gitignored build artifact)
├── src/
│   ├── fetch_reports.py       # Step 1: download Kantei HTMLs + table PNGs
│   ├── fetch_osm_stations.py  # Step 2: cache Tokyo station coords from OSM
│   ├── analysis.py            # Step 3: structured price data (DATA + VINTAGE)
│   ├── apply_update.py        # Step 3b: merge transcribed report JSON into analysis.py
│   ├── build_merged.py        # Step 4: join price data ↔ coords
│   ├── fetch_hazards.py       # Step 4b: Tokyo 地域危険度 ranks on e-Stat 町丁目 polygons
│   ├── fetch_rents.py         # Step 4c: SUUMO station rents now vs ~1yr ago (Internet Archive)
│   └── build_html.py          # Step 5: render Leaflet/HTML dashboard
├── data/
│   ├── urls.txt               # line-report IDs Kantei publishes
│   ├── merged.json            # Joined 584-station dataset (built artifact)
│   ├── tokyo_risk.json        # 5,190 町丁目 with collapse/fire/overall ranks (fetch_hazards.py)
│   ├── osm_stations.json      # OSM station cache (~1600 nodes, wide bbox)
│   ├── overpass_query.txt     # Reproduces the OSM query
│   └── image_urls.tsv         # PNG paths discovered on each report page
├── reports/                   # Cached Kantei HTML reports
└── images/                    # Cached Kantei data-table PNGs (canonical source)
```

## Pipeline

```
fetch_reports.py     → downloads HTML + PNG for each line in data/urls.txt
       ↓
   (manual)          → read each PNG and transcribe into analysis.DATA
       ↓
fetch_osm_stations.py → caches Tokyo station coordinates (rare — once a year)
       ↓
build_merged.py      → joins prices ↔ coords → data/merged.json
       ↓
build_html.py        → renders kantei.html
```

The transcription step is unavoidable: Kantei publishes the per-station tables
as **raster images, not text**. There's no API, no CSV, no embedded JSON.
Extraction requires either Claude vision (what was used here) or a Japanese
OCR pipeline like PaddleOCR/Tesseract. The 584 station rows in
`src/analysis.py` were transcribed from the PNG images in `images/` —
each image read by two independent vision agents with cell-level
reconciliation (2026-08 refresh: 20/20 images clean consensus).

To merge a new batch of refreshed reports: transcribe them into the JSON
shape documented in `src/apply_update.py`, then run
`python3 src/apply_update.py update.json` — it replaces superseded line
keys, records per-line vintage, and rewrites `analysis.py` in place.

## Data caveats (read these before drawing conclusions)

1. **Vintage isn't uniform.** Kantei publishes one line per week and rotates
   over ~24 months. As of the 2026-08 refresh:
   - 京王 / 井の頭 / 小田急 / 中央 / 青梅 / 江ノ島 / 多摩 / 西武新宿① / 東急目黒・多摩川:
     **2026-05 to 2026-08 (fresh)**
   - 東急 (東横, 田園都市, 池上, 大井町, 世田谷): 2026-03 to 2026-04
   - 京急①②③: 2026-02 · 京浜東北①②/根岸: 2025-11
   - 山手, メトロ, 都営, 総武, つくば: 2025
   - 埼京, 東武, 西武池袋: 2024 (oldest remaining)

   Every station row now carries its line's vintage (`VINTAGE` in
   analysis.py, surfaced in the dashboard popup and table). Treat
   absolute-growth comparisons across vintages with appropriate skepticism.

2. **Asking, not closing.** Kantei aggregates 売り希望価格 (asking prices). In a
   softening market, asking lags closing by 3–6 months.

3. **Sample-size variance.** Some stations (esp. small or premium-only lines)
   have tiny samples that swing the average. The avg-㎡ column is a partial
   tell — if it changes a lot YoY, the underlying unit mix changed too.

4. **Tony's specific picks were stripped from the public file.** This repo
   is the public-safe version: it contains aggregate market data only.

## Running it

Pure Python stdlib + `curl`. No external Python deps.

```bash
# Bootstrap (run once):
python3 src/fetch_reports.py        # downloads HTMLs + PNGs (~17 MB)
python3 src/fetch_osm_stations.py   # caches OSM coords (~1 MB)

# After editing analysis.DATA or refreshing data/osm_stations.json:
python3 src/build_merged.py
python3 src/fetch_hazards.py   # Tokyo risk polygons; downloads cached in data/raw/
python3 src/build_html.py      # local copy, includes data/picks.json if present
python3 src/build_html.py --public --out ../path/to/web/kantei.html   # deploy copy, no picks

# Open the result:
open kantei.html
```

To deploy: copy `kantei.html` to the Vercel project root (it's served as a
static file alongside the Notion dashboard at `/api/index`).

## Map controls (in the rendered dashboard)

- **Color metric**: 1-yr YoY / 2-yr cumulative / 2-yr CAGR
- **Affordability**: filter to stations where 60/70/80㎡ 2BR fits ¥100M
- **Min growth (1yr%)**: hide everything below a threshold
- **Line filter**: isolate one rail line
- Click a marker for full data popup. Sortable table below the map.
- **Rent metrics** (Color metric menu): `src/fetch_rents.py` scrapes SUUMO 家賃相場 line pages (マンション ワンルーム,
  asking rent) and compares each station with an Internet Archive copy from 9–24 months earlier, matched by SUUMO
  station code and annualised. "Rent − price" = rent change minus Kantei 1-yr price change, only where Kantei's
  vintage is late 2025 or newer. Each run saves `data/rents/YYYY-MM-DD.json` so our own history builds up.
  Basemap: drop a free CARTO key in `data/carto_key.txt` (gitignored) to use Voyager; otherwise 地理院タイル.
- **Hazards** (toggle row under the filters), with an opacity slider and a legend for active layers:
  - **Flood**: river flooding at maximum scale, rainwater (内水) or storm surge (高潮). Live tiles from
    MLIT's ハザードマップポータルサイト (keyless; credit required).
  - **Earthquake**: Tokyo building-collapse or overall rank per 町丁目, or J-SHIS (NIED) 2024 probability
    of 震度6弱+ shaking within 30 years via WMS. J-SHIS is near-uniformly high across Tokyo.
  - **Fire**: Tokyo fire-spread rank per 町丁目.
  - The Tokyo ranks come from 東京都「地震に関する地域危険度測定調査（第9回, 2022）」(CC BY), ranked 1 to 5
    relative within Tokyo, drawn on e-Stat 令和2年国勢調査 小地域 boundaries. They cover 東京都 only.
    Stations inside a ranked 町丁目 also show the ranks in their popup and in the 倒壊/火災 table columns.
  - Click the map with a Tokyo rank layer on to see that 町丁目's ranks.

## License

Source code: MIT.
Data: ©Tokyo Kantei. The PNG images and station-level price values are
republished from publicly available reports for personal due-diligence use.
Don't redistribute the raw images outside this repo.
