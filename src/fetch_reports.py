"""
Fetch Kantei 沿線・駅別 reports for Tokyo-area lines.

For each line ID in data/urls.txt, downloads:
  1. The HTML report page → reports/<id>.html
  2. The data-table PNG embedded in that page → images/<id>.png

Run:
    python3 src/fetch_reports.py

Idempotent: skips files that already exist. Run again to fetch only missing.
"""
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URLS = ROOT / "data" / "urls.txt"
HTML_DIR = ROOT / "reports"
IMG_DIR = ROOT / "images"
HTML_DIR.mkdir(exist_ok=True)
IMG_DIR.mkdir(exist_ok=True)

GENERIC = re.compile(r"iStock|cropped-favicon|alt-image|沿線別駅別|ico_iso|pic_company")
PNG_PAT = re.compile(r'src="([^"]*wp-content/uploads/[^"]+\.png)"')


def fetch(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        return True
    res = subprocess.run(
        ["curl", "-sL", "--fail", url, "-o", str(dest)], capture_output=True
    )
    return res.returncode == 0 and dest.exists() and dest.stat().st_size > 1000


def find_data_image(html: str) -> str | None:
    """Each Kantei line report embeds one canonical data-table PNG named after
    the line, e.g. /wp-content/uploads/東急東横線①（2026）.png. Skip stock photos."""
    for m in PNG_PAT.finditer(html):
        u = m.group(1)
        if not GENERIC.search(u):
            return u
    return None


def main() -> None:
    n_html, n_img = 0, 0
    with URLS.open() as f:
        for line in f:
            parts = line.strip().split(maxsplit=1)
            if len(parts) < 2:
                continue
            rid, name = parts
            html_path = HTML_DIR / f"{rid}.html"
            img_path = IMG_DIR / f"{rid}.png"

            url = f"https://www.kantei.ne.jp/report/wayside_station/{rid}/"
            if fetch(url, html_path):
                n_html += 1

            html = html_path.read_text(encoding="utf-8")
            png_path = find_data_image(html)
            if png_path:
                full = "https://www.kantei.ne.jp" + png_path
                if fetch(full, img_path):
                    n_img += 1

    print(f"Fetched {n_html} HTMLs and {n_img} PNGs")
    print(f"  reports → {HTML_DIR}")
    print(f"  images  → {IMG_DIR}")


if __name__ == "__main__":
    main()
