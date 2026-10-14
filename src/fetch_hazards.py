"""Build data/tokyo_risk.json: Tokyo 地域危険度 (第9回) ranks drawn on 町丁目 polygons.

Sources (credit required, both CC BY-compatible):
- 東京都都市整備局「地震に関する地域危険度測定調査（第9回）」(2022-09) all2.csv, 5,192 町丁目
- 総務省統計局 e-Stat 境界データ: 令和2年国勢調査 小地域 (東京都, 世界測地系 緯度経度, Shapefile)

Pure stdlib. Downloads are cached in data/raw/ (gitignored); delete them to refetch.
Output: {"meta": ..., "towns": [[label, collapse_rank, fire_rank, total_rank, [ring, ...]], ...]}
where each ring is delta-encoded ints at 1e-5 degrees: [x0, y0, dx1, dy1, ...] (x = lon).
"""
import csv
import io
import json
import re
import struct
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RISK_URL = "https://www.toshiseibi.metro.tokyo.lg.jp/bosai/chousa_6/download/all2.csv?2209="
ESTAT_URL = ("https://www.e-stat.go.jp/gis/statmap-search/data?dlserveyId=A002005212020"
             "&code=13&coordSys=1&format=shape&downloadType=5&datum=2011")
TOL = 0.00008  # Douglas-Peucker tolerance in degrees (about 8m)


def fetch(url, path):
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        path.write_bytes(urllib.request.urlopen(req, timeout=180).read())
    return path.read_bytes()


KANJI = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def kanji_int(s):
    n = cur = 0
    for ch in s:
        if ch == "十":
            n += (cur or 1) * 10
            cur = 0
        else:
            cur = KANJI[ch]
    return n + cur


def norm(name):
    """'北烏山一丁目' and '北烏山１丁目' both become '北烏山1丁目'; old kanji forms folded."""
    name = name.translate(str.maketrans("０１２３４５６７８９ヶ濤鶯", "0123456789ケ涛鴬")).replace(" ", "").replace("　", "")
    return re.sub(r"([一二三四五六七八九十]+)丁目", lambda m: f"{kanji_int(m.group(1))}丁目", name)


def city_norm(city):
    return re.sub(r"^.*郡", "", city).replace(" ", "").replace("　", "")


def lookup(polys, city, town):
    """Match a survey 町丁目 to census polygons. The 2022 survey uses some names that differ
    from the 2020 census (神田 prefixes, 四谷 prefixes, 大字, 丁目 granularity)."""
    city, t = city_norm(city), norm(town)
    for c in (t, t.removeprefix("大字"), t.removeprefix("神田"), "四谷" + t, re.sub(r"\d+丁目$", "", t)):
        if (city, c) in polys:
            return polys[(city, c)]
    parts = [r for (cy, n), r in polys.items() if cy == city and re.fullmatch(re.escape(t) + r"\d+丁目", n)]
    return [ring for r in parts for ring in r] or None


def read_dbf(b):
    n, hlen, rlen = struct.unpack("<IHH", b[4:12])
    fields, off = [], 32
    while b[off] != 0x0D:
        fields.append((b[off:off + 11].split(b"\0")[0].decode(), b[off + 16]))
        off += 32
    rows = []
    for i in range(n):
        r, p, d = b[hlen + i * rlen: hlen + (i + 1) * rlen], 1, {}
        for name, ln in fields:
            d[name] = r[p:p + ln].decode("cp932", "replace").strip()
            p += ln
        rows.append(d)
    return rows


def read_shp(b):
    shapes, off = [], 100
    while off < len(b):
        clen = struct.unpack(">i", b[off + 4:off + 8])[0] * 2
        c = b[off + 8: off + 8 + clen]
        off += 8 + clen
        if struct.unpack("<i", c[:4])[0] == 0:
            shapes.append([])
            continue
        nparts, npts = struct.unpack("<2i", c[36:44])
        parts = struct.unpack(f"<{nparts}i", c[44:44 + 4 * nparts])
        xy = struct.unpack(f"<{2 * npts}d", c[44 + 4 * nparts: 44 + 4 * nparts + 16 * npts])
        rings = []
        for i, s in enumerate(parts):
            e = parts[i + 1] if i + 1 < nparts else npts
            rings.append([(xy[2 * j], xy[2 * j + 1]) for j in range(s, e)])
        shapes.append(rings)
    return shapes


def simplify(pts, tol):
    if len(pts) < 5:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack, tol2 = [(0, len(pts) - 1)], tol * tol
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        seg = dx * dx + dy * dy
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            t = 0.0 if seg == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg))
            d = (ax + t * dx - px) ** 2 + (ay + t * dy - py) ** 2
            if d > best:
                best, idx = d, i
        if best > tol2:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def encode(ring):
    out, px, py = [], 0, 0
    for x, y in ring:
        ix, iy = round(x * 1e5), round(y * 1e5)
        out += [ix - px, iy - py]
        px, py = ix, iy
    return out


RAW.mkdir(parents=True, exist_ok=True)
risk_csv = fetch(RISK_URL, RAW / "tokyo_chiiki_kikendo_9.csv").decode("cp932")
z = zipfile.ZipFile(io.BytesIO(fetch(ESTAT_URL, RAW / "estat_r2ka13.zip")))
attrs = read_dbf(z.read("r2ka13.dbf"))
shapes = read_shp(z.read("r2ka13.shp"))
assert len(attrs) == len(shapes)

# Group e-Stat polygons by (city, normalised 町丁目), skipping water areas (HCODE 8154).
polys = {}
for a, rings in zip(attrs, shapes):
    if a["HCODE"] == "8154" or not a["S_NAME"]:
        continue
    for part in norm(a["S_NAME"]).split("，"):  # e.g. '入谷町，舎人町' is one census polygon
        polys.setdefault((city_norm(a["CITY_NAME"]), part), []).extend(rings)

towns, unmatched = [], []
for row in csv.DictReader(io.StringIO(risk_csv)):
    rings = lookup(polys, row["区市町名"], row["町丁目名"])
    if not rings:
        unmatched.append(row["区市町名"] + row["町丁目名"])
        continue
    enc = []
    for ring in rings:
        s = simplify(ring, TOL)
        if len(s) >= 4:
            enc.append(encode(s))
    towns.append([f'{city_norm(row["区市町名"])} {row["町丁目名"]}', int(row["建物倒壊危険度ランク"]),
                  int(row["火災危険度ランク"]), int(row["総合危険度ランク"]), enc])

out = {
    "meta": {
        "survey": "東京都 地震に関する地域危険度測定調査（第9回, 2022-09公表）",
        "boundaries": "e-Stat 境界データ 令和2年国勢調査 小地域（東京都）",
        "ranks": "1 (lowest) to 5 (highest), relative within Tokyo",
        "built": date.today().isoformat(),
        "matched": len(towns),
        "unmatched": unmatched,
    },
    "towns": towns,
}
path = ROOT / "data" / "tokyo_risk.json"
path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"Matched {len(towns)} 町丁目, unmatched {len(unmatched)}: {unmatched[:15]}")
print(f"Wrote {path} ({path.stat().st_size // 1024} KB)")
