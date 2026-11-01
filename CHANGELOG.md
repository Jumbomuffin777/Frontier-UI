# Changelog

## 1.1.1 — 2026-11-01
- **Renamed to Frontier UI** (formerly Intelligent WebUI). The tool file is now `frontier_ui.py`, the tool id `frontier_ui`
  and the main method `render_frontier_ui`. Upgrading: install the new file, copy your valves over, and enable it on your
  models in place of the old one.

## 1.1.0 — 2026-11-01

**New blocks**
- `weather` — live forecast (Open-Meteo, keyless): now, 24-hour curve, daily strip.
- `stock` — live quotes with 1D / 1M / 1Y charts and a 52-week range (Yahoo Finance chart API, keyless). Stocks, crypto, commodities, FX.
- `budget` — interactive cost sliders, people stepper, per-person totals, category bar and an optional budget cap.
- `calculator` — sliders and number inputs feeding formulas (safe parser, no `eval`; `pmt`, `fv`, `pv`, `if`, …).
- `links` — page preview cards: headless-Chromium screenshot, title, summary and a reader view.
- `email` — ready-to-send draft with **Open in Gmail**, copy, or any mail app.
- `status` — service / health boards.
- `apps` — launcher for all 13 Craft apps.

**Better maps & cards**
- Multi-day trips: `"days":[…]` gives day tabs and one coloured street route per day; the timeline follows the selected day.
- **Open in Google Maps** for the whole route or any single stop.
- Self-hosted basemap: point `tiles_url` at a Protomaps planet PMTiles + fonts + JS and maps never touch a third-party tile server
  (automatic fallback to OpenFreeMap, then raster).
- Place cards with 4+ items get sort (rating, price, name) and filter chips (price, tags, 4.5★+).
- Sortable table columns; fuzzy matching between timeline rows and map pins.

**Actions on every card**: Copy, Email (Gmail), Add to calendar (Google Calendar or `.ics`), Export (Word, PDF, Excel, PowerPoint)
and Save to Notes.

**New tool methods**
- `craft_file` — real `.docx` / `.pdf` / `.odt` / `.rtf` / `.xlsx` / `.csv` / `.pptx` files built by the Craft apps' own engines
  (WordCraft, GridCraft, DeckCraft); a whole card exports by id, photos and charts included. Optionally opens the file on the
  streamed Craft desktop.
- `craft_open` — open an image, PDF, SVG, audio or video URL in PhotoCraft, PdfCraft, VectorCraft, SoundCraft, FilmCraft…
- `save_note` — save a card or any Markdown to Open WebUI Notes.

**Smarter**
- Reuses Open WebUI's own embedding engine (e.g. EmbeddingGemma) to rerank photos and link itinerary rows to map pins.
- SSRF guards on every server-side fetch; the Craft bridge only accepts a shared token on the internal Docker network.

## 1.0.0 — 2026-11-01
First release: photo galleries, live street maps with routes, place cards, itineraries, charts, tables, citations and follow-ups.
