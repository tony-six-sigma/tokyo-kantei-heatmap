# Launch / social copy

Short blurbs for sharing the heatmap. Three angles, plus deep-cut lines for
technical audiences.

Live URL: https://web-tony-six-sigmas-projects.vercel.app/kantei.html

---

## A. Pure flex (single slide)

```
Tokyo capital-gains heatmap
436 stations · 42 train lines · 3yrs of data · 1 day

🔗 web-tony-six-sigmas-projects.vercel.app/kantei.html
```

## B. Build log (one or two slides)

```
🇯🇵 What's going up in Tokyo. What's not.

• 74 Kantei reports scraped
• Tokyo Kantei publishes per-station ¥/坪 as PNG tables.
  No API. No CSV. No JSON.
• Claude vision OCR'd all 74 Japanese tables → 436 stations
• OpenStreetMap Overpass API → 1,200 station coords
• 100% match rate after 6 manual fixes
• Pure Python stdlib + curl. No pip. No npm.
• Single 121 KB self-contained HTML. Leaflet + CartoDB tiles.
• Public URL for my agent. Gitignored picks overlay for me.
```

## C. Headline numbers

```
Built today:

📊 1,308 data points
🚉 436 Tokyo stations
🚇 42 train lines
📁 121 KB single file
⏱  ~1 day end-to-end
```

---

## Deep-cut lines (for technical audiences)

- *"Tokyo Kantei's 沿線・駅別 reports are PNG raster tables. The unlock was:
  Claude reads images. Skipped writing a Tesseract pipeline entirely."*

- *"Vintage isn't uniform — Kantei publishes one line per week and rotates
  ~24 months. So the dashboard mixes 2024-snapshot 京王 with 2026-snapshot
  東急. Annotated that caveat in the README so future-me doesn't get
  fooled."*

- *"Zero npm, zero pip. Just `python3` and `curl`. ~700 lines of code total."*

- *"Public sanitized version on Vercel + private annotated overlay via
  gitignored `picks.json`. Same codebase, two surfaces. Share with your
  agent without leaking your shortlist."*

---

## Suggested IG-story sequence (3 slides)

**Slide 1** — hook
> Built a Tokyo real estate capital-gains heatmap from scratch in a day.
> 436 stations. 42 train lines. 1,308 data points.

**Slide 2** — the technical thing that's actually interesting
> The data lives as raster PNGs on Kantei's site. No API exists.
> Claude vision read all 74 Japanese tables for me.
> Pure stdlib Python + curl. No pip, no npm.

**Slide 3** — link / CTA
> 🔗 web-tony-six-sigmas-projects.vercel.app/kantei.html
> Color = 1yr YoY. Size = sub-¥100M affordability.
> Hover any dot.
