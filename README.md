# tokyo-kantei-heatmap

Interactive Tokyo capital-gains heatmap built from Tokyo Kantei's
**沿線・駅別中古マンション平均坪単価** reports. Plots ~436 stations across 42
Tokyo-area train lines, color-coded by 1-year YoY ¥/坪 change and sized by
sub-¥100M affordability — meant for spotting which areas are still going up
and which have rolled over.

**Live deployment:** https://web-tony-six-sigmas-projects.vercel.app/kantei.html

![preview](kantei.html)

---

## What's in here

```
.
├── kantei.html               # Built dashboard (single self-contained file)
├── src/
│   ├── fetch_reports.py       # Step 1: download Kantei HTMLs + table PNGs
│   ├── fetch_osm_stations.py  # Step 2: cache Tokyo station coords from OSM
│   ├── analysis.py            # Step 3: structured price data + ranking
│   ├── build_merged.py        # Step 4: join price data ↔ coords
│   └── build_html.py          # Step 5: render Leaflet/HTML dashboard
├── data/
│   ├── urls.txt               # 74 line-report IDs Kantei publishes
│   ├── merged.json            # Joined 436-station dataset (built artifact)
│   ├── osm_stations.json      # OSM Tokyo stations cache (~1200 nodes)
│   ├── overpass_query.txt     # Reproduces the OSM query
│   └── image_urls.tsv         # PNG paths discovered on each report page
├── reports/                   # Cached Kantei HTML reports (74 files)
└── images/                    # Cached Kantei data-table PNGs (74 files)
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

The "manual" step is unavoidable: Kantei publishes the per-station tables as
**raster images, not text**. There's no API, no CSV, no embedded JSON.
Extraction requires either Claude vision (what was used here) or a Japanese
OCR pipeline like PaddleOCR/Tesseract. The 436 station rows in
`src/analysis.py` were transcribed from the PNG images in `images/`.

If Kantei refreshes a line, refetch its report and re-transcribe just the new
table — most stations and lines stay stable.

## Data caveats (read these before drawing conclusions)

1. **Vintage isn't uniform.** Kantei publishes one line per week and rotates
   over ~24 months. As of this build:
   - 東急 lines (東横, 田園都市, 池上, 大井町, 目黒, 多摩川): 2026-03 to 2026-04
   - 京急 lines: 2026-02
   - 山手, 中央, 京浜東北②, メトロ, 都営: mid-to-late 2025
   - **京王, 京王井の頭, 小田急, 西武, 中央①②, 埼京: 2024-06 to 2024-09 (still latest)**

   So a station's "1-yr YoY" depends on when Kantei sampled — comparing a
   2026-04 reading on 田園都市 against a 2024-08 reading on 京王 is comparing
   different points in the cycle. The dashboard surfaces this implicitly via
   the *line* label; treat absolute-growth comparisons across vintages with
   appropriate skepticism.

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
python3 src/build_html.py

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

## License

Source code: MIT.
Data: ©Tokyo Kantei. The PNG images and station-level price values are
republished from publicly available reports for personal due-diligence use.
Don't redistribute the raw images outside this repo.
