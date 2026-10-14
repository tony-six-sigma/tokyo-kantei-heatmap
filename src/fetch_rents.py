"""Station rents and ~1-year rent change from SUUMO 家賃相場 line pages.

SUUMO's per-line 家賃相場 pages list every station's average asking rent for the page's default
filter (マンション, ワンルーム), the classic investor product. A year-ago copy of each page comes
from the Internet Archive (Wayback Machine). Rent change = today vs the archived copy closest to
one year ago (at least 9 months old), annualised. Stations are matched across time by SUUMO's
station code (ek_xxxxx). Each run also saves today's scrape to data/rents/ so our own history
builds up and later runs can drop the Wayback dependency.

Pure stdlib. Raw pages are cached in data/raw/rents/ (gitignored).
Output data/station_rents.json:
  {"meta": ..., "stations": {"<kantei line>|<station>": [rent_now, rent_then, then_date, change_pct_per_yr]}}
"""
import gzip
import json
import re
import urllib.error
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "rents"
TODAY = date.today()
PREFS = ("tokyo", "kanagawa", "saitama", "chiba")
ROW = re.compile(r'<tr class="js-graph-data" data-value="([\d.]+)">\s*<td><a href="/chintai/soba/\w+/ek_(\d+)/[^"]*">([^<]+)</a>')
# Heatmap line part -> SUUMO line names (SUUMO's Tokyo page calls the Odakyu main line 小田急線,
# and Kantei's 東京臨海 report also covers ゆりかもめ stations)
SUUMO_NAMES = {"東京臨海": ["りんかい線", "ゆりかもめ"], "大井町線": ["東急大井町線"],
               "小田急小田原線": ["小田急小田原線", "小田急線"]}


def get(url, cache=None, tries=4):
    """Fetch with a cache file; back off on the Internet Archive's 429/503 throttling."""
    if cache and cache.exists():
        return cache.read_text(encoding="utf-8")
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=90).read()
            if raw[:2] == b"\x1f\x8b":  # the Archive's raw (id_) copies come back gzipped
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8", "replace")
            if cache:
                cache.write_text(text, encoding="utf-8")
            return text
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
            time.sleep(10 * 2 ** i)


def parse(html):
    """{ek_code: (station name, rent 万円)} for one line page."""
    return {ek: (name.strip(), float(v)) for v, ek, name in ROW.findall(html) if float(v) > 0}


def suumo_lines(kantei_line):
    names = re.sub(r"[①②③]", "", kantei_line).replace("JR", "ＪＲ").split("・")
    return [m for n in names if n for m in SUUMO_NAMES.get(n, [n])]


def norm_station(name):
    return re.sub(r"[（(].*?[)）]", "", name).replace("ケ", "ヶ").replace("ッ", "ツ").strip()


RAW.mkdir(parents=True, exist_ok=True)
(ROOT / "data" / "rents").mkdir(exist_ok=True)

# SUUMO line index: line name -> [(pref, slug)]
index = {}
for pref in PREFS:
    html = get(f"https://suumo.jp/chintai/soba/{pref}/ensen/", RAW / f"index_{pref}_{TODAY}.html")
    for slug, name in re.findall(r'href="/chintai/soba/' + pref + r'/(en_[a-z0-9_]+)/"[^>]*>\s*([^<]+?)\s*<', html):
        index.setdefault(name.strip(), []).append((pref, slug))

rows = json.loads((ROOT / "data" / "merged.json").read_text(encoding="utf-8"))
pages = sorted({p for r in rows for n in suumo_lines(r["line"]) for p in index.get(n, [])})
print(f"{len(pages)} SUUMO line pages")

now, then, then_dates, no_archive = {}, {}, {}, []
for pref, slug in pages:
    now[(pref, slug)] = parse(get(f"https://suumo.jp/chintai/soba/{pref}/{slug}/", RAW / f"{pref}_{slug}_{TODAY}.html"))


def closest_snapshot(url):
    """Archived copy closest to one year ago that is at least ~9 months old (availability API)."""
    for days_back in (365, 450, 300):
        target = date.fromordinal(TODAY.toordinal() - days_back).strftime("%Y%m%d")
        cache = RAW / f"avail_{url.split('/soba/')[1].strip('/').replace('/', '_')}_{target}.json"
        snap = json.loads(get(f"https://archive.org/wayback/available?url={url}&timestamp={target}", cache))
        c = snap.get("archived_snapshots", {}).get("closest")
        if c and c.get("status") == "200":
            ts = c["timestamp"]
            if 270 <= TODAY.toordinal() - datetime.strptime(ts[:8], "%Y%m%d").toordinal() <= 730:
                return ts
    return None


for pref, slug in pages:
    url = f"suumo.jp/chintai/soba/{pref}/{slug}/"
    try:
        ts = closest_snapshot(url)
        if ts:
            old = get(f"https://web.archive.org/web/{ts}id_/https://{url}", RAW / f"wb_{pref}_{slug}_{ts}.html")
            then[(pref, slug)] = parse(old)
            then_dates[(pref, slug)] = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
        else:
            no_archive.append(f"{pref}/{slug}")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        no_archive.append(f"{pref}/{slug} ({e})")
    print(f"{pref}/{slug}: now {len(now[(pref, slug)])} stations, then {len(then.get((pref, slug), {}))} "
          f"({then_dates.get((pref, slug), 'no archive')})", flush=True)
    time.sleep(1.5)

# Save today's scrape (our own history for future runs)
snap = {f"{p}/{s}": {ek: [n, v] for ek, (n, v) in d.items()} for (p, s), d in now.items()}
(ROOT / "data" / "rents" / f"{TODAY}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")

# Station codes (ek_xxxxx) are stable, so match old and new rents by code across every page.
# A line's archived page in one prefecture often covers stations missing from another's archive.
then_by_ek = {}
for page, d in then.items():
    for ek, (_, rent) in d.items():
        then_by_ek.setdefault(ek, (rent, then_dates[page]))
now_names = {}  # normalised station name -> {ek: rent}, line pages first, any page as fallback
for page, d in now.items():
    for ek, (name, rent) in d.items():
        now_names.setdefault(norm_station(name), {})[ek] = rent

out, missing = {}, []
for r in rows:
    target = norm_station(r["station"])
    hit = None
    for n in suumo_lines(r["line"]):
        for page in index.get(n, []):
            for ek, (name, rent) in now.get(page, {}).items():
                if norm_station(name) == target:
                    hit = (ek, rent)
                    break
            if hit:
                break
        if hit:
            break
    if not hit and len(now_names.get(target, {})) == 1:  # e.g. 笹塚 listed only on the 京王線 page
        hit = next(iter(now_names[target].items()))
    if not hit:
        missing.append(f'{r["line"]}|{r["station"]}')
        continue
    ek, rent = hit
    old, d = then_by_ek.get(ek, (None, None))
    chg = None
    if old:
        days = TODAY.toordinal() - date.fromisoformat(d).toordinal()
        chg = round(((rent / old) ** (365 / days) - 1) * 100, 1)
    out[f'{r["line"]}|{r["station"]}'] = [rent, old, d, chg]

meta = {
    "source": "SUUMO 家賃相場 line pages (マンション, ワンルーム default view); year-ago copies via Internet Archive",
    "scraped": TODAY.isoformat(),
    "stations": len(out),
    "with_change": sum(1 for v in out.values() if v[3] is not None),
    "missing": missing,
    "no_archive": no_archive,
}
path = ROOT / "data" / "station_rents.json"
path.write_text(json.dumps({"meta": meta, "stations": out}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{len(out)} stations with rent, {meta['with_change']} with a ~1yr change; missing {len(missing)}: {missing[:12]}")
