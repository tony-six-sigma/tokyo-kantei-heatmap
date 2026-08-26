"""
Merge analysis.DATA with OSM station coordinates → data/merged.json.

Run once after editing analysis.DATA or refreshing data/osm_stations.json.
Output is consumed by build_html.py.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import analysis  # noqa: E402
from analysis import DATA  # noqa: E402

VINTAGE = getattr(analysis, "VINTAGE", {})

OSM_PATH = ROOT / "data" / "osm_stations.json"
OUT_PATH = ROOT / "data" / "merged.json"


def normalize(name: str) -> str:
    """Strip '(line)' suffixes that Kantei datasets sometimes add for stations
    appearing on multiple lines, e.g. '下北沢(京王)' → '下北沢'."""
    return re.sub(r"\([^)]+\)", "", name).strip()


def load_osm_index() -> dict[str, list[dict]]:
    with OSM_PATH.open(encoding="utf-8") as f:
        osm = json.load(f)
    index: dict[str, list[dict]] = defaultdict(list)
    for el in osm.get("elements", []):
        tags = el.get("tags", {})
        name_ja = tags.get("name:ja") or tags.get("name")
        if not name_ja:
            continue
        clean = name_ja.replace("駅", "").strip()
        index[clean].append({"lat": el.get("lat"), "lon": el.get("lon")})
    return index


# Manual coords for stations that fall outside the OSM Tokyo bounding box or
# have alternate name encodings the index missed.
MANUAL_COORDS = {
    ("東京メトロ副都心線", "明治神宮前"): (35.6688, 139.7058),
    ("東京メトロ半蔵門線", "押上"): (35.7100, 139.8131),
    ("東京メトロ丸ノ内線①", "四ッ谷"): (35.6857, 139.7310),
    ("東京メトロ丸ノ内線②", "南阿佐ヶ谷"): (35.6970, 139.6361),
    ("京急本線②", "黄金町"): (35.4421, 139.6249),
    ("京急本線②", "上大岡"): (35.3963, 139.5906),
}


def main() -> None:
    osm_index = load_osm_index()
    rows = []
    matched = 0
    unmatched: list[tuple[str, str]] = []

    for line, stations in DATA.items():
        for entry in stations:
            station, p, age, sqm, p1, age1, sqm1, p2, age2, sqm2 = entry
            norm = normalize(station)
            candidates = osm_index.get(norm) or osm_index.get(
                norm.replace("ヶ", "ケ").replace("ケ", "ヶ")
            )
            if candidates:
                lat, lon = candidates[0]["lat"], candidates[0]["lon"]
                matched += 1
            elif (line, station) in MANUAL_COORDS:
                lat, lon = MANUAL_COORDS[(line, station)]
                matched += 1
            else:
                lat, lon = None, None
                unmatched.append((line, station))

            yoy_1 = (p / p1 - 1) * 100 if p1 > 0 else None
            yoy_2 = (p / p2 - 1) * 100 if p2 > 0 else None
            cagr = ((p / p2) ** 0.5 - 1) * 100 if p2 > 0 else None

            rows.append(
                {
                    "line": line,
                    "station": station,
                    "norm": norm,
                    "lat": lat,
                    "lon": lon,
                    "p_now": p,
                    "p_1y": p1,
                    "p_2y": p2,
                    "vintage": VINTAGE.get(line, "?"),
                    "yoy_1": yoy_1,
                    "yoy_2": yoy_2,
                    "cagr_2": cagr,
                    "max_sqm_100m": 33060 / p,
                    "avg_sqm": sqm,
                    "avg_age": age,
                }
            )

    OUT_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Total rows : {len(rows)}")
    print(f"Matched    : {matched}  ({100 * matched / len(rows):.1f}%)")
    print(f"Unmatched  : {len(unmatched)}")
    for line, st in unmatched[:10]:
        print(f"  - {line}: {st}")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
