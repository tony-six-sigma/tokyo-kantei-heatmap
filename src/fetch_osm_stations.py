"""
Fetch all railway stations within the Tokyo metropolitan bounding box
from OpenStreetMap via the Overpass API → data/osm_stations.json.

Heavy call; only re-run if station list goes stale (rare). Otherwise
the cached snapshot is fine.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "osm_stations.json"
QUERY = ROOT / "data" / "overpass_query.txt"

if not QUERY.exists():
    QUERY.write_text(
        """[out:json][timeout:90];
(
  node["railway"="station"](35.45,139.30,35.95,140.05);
  node["station"="subway"](35.45,139.30,35.95,140.05);
);
out tags center;
""",
        encoding="utf-8",
    )

print("Querying Overpass API …")
res = subprocess.run(
    [
        "curl",
        "-sL",
        "--data-urlencode",
        f"data@{QUERY}",
        "https://overpass-api.de/api/interpreter",
        "-o",
        str(OUT),
    ]
)
size = OUT.stat().st_size if OUT.exists() else 0
print(f"Wrote {OUT} ({size // 1024} KB)")
