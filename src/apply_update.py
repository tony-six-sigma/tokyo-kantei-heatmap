"""
Merge transcribed Kantei report JSON into analysis.py's DATA literal.

Input: one or more JSON files, each shaped as the transcription workflow output:
  { "reports": [ { "id", "title", "date", "data": { "sections": [
      { "line", "stations": [ { "name", "cur": [p,age,sqm], "y1": [...], "y2": [...] } ] } ] } } ] }

For each report, the title is mapped to a DATA key (see KEY_MAP; unmapped
titles become new keys verbatim). The line's station list is REPLACED
wholesale, and VINTAGE[key] is set to the report date.

Regenerates analysis.py in place: the DATA = {...} block is rewritten from
the merged in-memory dict, a VINTAGE = {...} block is written after it, and
everything else in the file is preserved.

Run:
    python3 src/apply_update.py update1.json [update2.json ...]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import analysis  # noqa: E402

ANALYSIS_PATH = ROOT / "src" / "analysis.py"

# report title (from workflow item) -> existing DATA key to replace.
# Titles not listed here become new DATA keys under their own name.
KEY_MAP = {
    "西武新宿線①": "西武新宿線①",
    "京王相模原線・京王高尾線": "京王相模原線・高尾線",
    "京王新線・京王井の頭線": "京王新線・京王井の頭線",
    "京王線②": "京王線②",
    "京王線①": "京王線①",
    "JR中央線②": "JR中央線②",
    "JR中央線①": "JR中央線①",
    "小田急小田原線②": "小田急小田原線②",
    "小田急小田原線①": "小田急小田原線①",
    "東急多摩川線": "東急多摩川線",
    "東急目黒線": "東急目黒線",
    "京急本線①": "京急本線①",
    "京急本線②": "京急本線②",
}

# Report title -> old DATA keys made obsolete by this report (e.g. a combined
# key that the refreshed report now publishes as separate line sections).
SUPERSEDES = {
    "京王新線・京王井の頭線": ["京王新線・京王井の頭線"],
    "京王相模原線・京王高尾線": ["京王相模原線・高尾線"],
    "JR京浜東北線①": ["JR京浜東北線"],
}

# Vintage labels for lines NOT touched by an update file (from build history).
BASE_VINTAGE = {
    "東急東横線①": "2026-04", "東急東横線②": "2026-04",
    "東急田園都市線①": "2026-04", "東急田園都市線②": "2026-04",
    "東急池上線": "2026-03", "東急大井町線②": "2026-03",
    "東急世田谷線・大井町線①": "2026-03",
    "東京メトロ副都心線": "2025", "東京メトロ有楽町線①": "2025",
    "東京メトロ有楽町線②": "2025", "東京メトロ半蔵門線": "2025",
    "東京メトロ日比谷線①": "2025", "東京メトロ日比谷線②": "2025",
    "東京メトロ千代田線": "2025", "東京メトロ銀座線": "2025",
    "東京メトロ丸ノ内線①": "2025", "東京メトロ丸ノ内線②": "2025",
    "東京メトロ東西線①": "2025", "東京メトロ東西線②": "2025",
    "東京メトロ南北線①": "2025", "東京メトロ南北線②": "2025",
    "都営大江戸線①": "2025", "都営大江戸線②": "2025",
    "都営浅草線": "2025", "都営新宿線①": "2025", "都営新宿線②": "2025",
    "都営三田線①": "2025", "都営三田線②": "2025",
    "JR山手線①": "2025", "JR山手線②": "2025",
    "JR総武線①": "2024-25", "JR総武線②": "2024-25",
    "JR埼京線": "2024", "つくばエクスプレス": "2025",
    "東武東上線①": "2024", "東武伊勢崎線①": "2024",
    "西武池袋線①": "2024", "西武池袋線②": "2024",
    "東京臨海": "2025",
}


def fmt_num(x) -> str:
    """Ints without decimal point, floats with one decimal."""
    if isinstance(x, float) and x == int(x):
        return str(int(x))
    return str(x)


def render_data_literal(data: dict) -> str:
    out = ["DATA = {"]
    for line, stations in data.items():
        out.append(f'    "{line}": [')
        for st in stations:
            name, *nums = st
            nums_s = ", ".join(fmt_num(n) for n in nums)
            out.append(f'        ("{name}", {nums_s}),')
        out.append("    ],")
    out.append("}")
    return "\n".join(out)


def render_vintage_literal(vintage: dict) -> str:
    out = ["", "# Per-line data vintage (Kantei report publication date/period)", "VINTAGE = {"]
    for k, v in vintage.items():
        out.append(f'    "{k}": "{v}",')
    out.append("}")
    return "\n".join(out)


def main() -> None:
    update_files = sys.argv[1:]
    if not update_files:
        sys.exit("usage: apply_update.py update1.json [update2.json ...]")

    data = dict(analysis.DATA)  # preserves insertion order
    vintage = dict(BASE_VINTAGE)
    # carry forward existing vintages if analysis already has them
    vintage.update(getattr(analysis, "VINTAGE", {}))

    replaced, added, removed = [], [], []
    for uf in update_files:
        payload = json.loads(Path(uf).read_text(encoding="utf-8"))
        for rep in payload["reports"]:
            for old_key in SUPERSEDES.get(rep["title"].strip(), []):
                if old_key in data:
                    del data[old_key]
                    removed.append(old_key)
            date = rep["date"].replace(".", "-")[:7]  # YYYY-MM
            secs = rep["data"]["sections"]
            # Single-section reports keep the report title as the key;
            # multi-section reports get one key per section header.
            multi = len(secs) > 1
            for sec in secs:
                title = sec["line"].strip() if multi else rep["title"].strip()
                key = KEY_MAP.get(title, title)
                rows = [
                    (
                        st["name"].replace("　", "").replace(" ", ""),
                        *st["cur"], *st["y1"], *st["y2"],
                    )
                    for st in sec["stations"]
                ]
                if key in data:
                    replaced.append(key)
                else:
                    added.append(key)
                data[key] = rows
                vintage[key] = date

    # default vintage for anything still unlabeled
    for k in data:
        vintage.setdefault(k, "?")
    # drop vintage entries for keys that no longer exist
    vintage = {k: v for k, v in vintage.items() if k in data}

    src = ANALYSIS_PATH.read_text(encoding="utf-8")
    m = re.search(r"^DATA = \{.*?^\}", src, re.S | re.M)
    if not m:
        sys.exit("could not locate DATA literal in analysis.py")
    new_block = render_data_literal(data)
    src = src[: m.start()] + new_block + src[m.end():]

    # replace or insert VINTAGE block
    vm = re.search(
        r"\n# Per-line data vintage.*?^VINTAGE = \{.*?^\}", src, re.S | re.M
    )
    vintage_block = render_vintage_literal(vintage)
    if vm:
        src = src[: vm.start()] + "\n" + vintage_block + src[vm.end():]
    else:
        dm = re.search(r"^DATA = \{.*?^\}", src, re.S | re.M)
        src = src[: dm.end()] + "\n" + vintage_block + src[dm.end():]

    ANALYSIS_PATH.write_text(src, encoding="utf-8")
    total = sum(len(v) for v in data.values())
    print(f"Lines replaced : {len(replaced)} -> {replaced}")
    print(f"Lines added    : {len(added)} -> {added}")
    print(f"Keys removed   : {len(removed)} -> {removed}")
    print(f"Total lines    : {len(data)}   Total station rows: {total}")
    print(f"Rewrote {ANALYSIS_PATH}")


if __name__ == "__main__":
    main()
