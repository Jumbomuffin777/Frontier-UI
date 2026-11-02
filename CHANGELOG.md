# Changelog

## 1.3.1 — 2026-11-02
**Photos for long queries, a self-starting Craft bridge, Apple Silicon.** Thanks to
[@ondrejch](https://github.com/ondrejch) for PR #1 and to u/PersonalCitron2328 for the Mac report.

- **Photos for long or descriptive queries** (PR #1 by @ondrejch): "brown tabby Maine Coon cat" used to come back empty
  because the Wikipedia/Commons matcher scores title overlap against the whole query. When a query finds fewer than three
  photos it now tops up from shorter heads (the caption before a dash, the last/first two words). Photos load eagerly,
  the tool asks the model for 2-6 word photo queries, and `build.sh` strips a leading BOM per part (which also fixes the
  BOM handling in the spec parser that 1.3.0's build broke).
- Follow-ups to PR #1: the shorter searches run in parallel inside what is left of the 8 s photo budget, and whatever the
  original query found is always kept, so a slow fallback can't blank a tile. Word-fragment fallbacks are only used for
  gallery and hero photos - place cards don't get a photo of "Shibuya Tokyo" for "Ichiran Ramen Shibuya Tokyo".
- **Craft bridge starts with the container**: it now runs as an s6 service defined inline in
  `server/craft-apps/docker-compose.yml` (no more `docker exec ... bridge.py` after every restart, and s6 restarts it if it
  stops). Existing installs: update the compose file and run `docker compose up -d`; the old desktop-autostart line can go.
- **Apple Silicon / ARM hosts**: `platform: linux/amd64` in the Craft compose file (the image is x86-64 only).
- Maps: route lines are re-added whenever the map settles, so they survive a basemap fallback (self-hosted ->
  OpenFreeMap -> raster) or a theme switch; previously that could leave pins without a line.
- Craft bridge: new `/cli` endpoint so agents can run any app's command line in a scratch folder (token-protected,
  no absolute paths, no servers or code execution).
- Tests: long-query top-up, place cards without fragment fallbacks, slow fallback keeps the original photos.

## 1.3.0 — 2026-11-01
**Works out of the box with no SearXNG and no keys, metric/imperial, reliable routes and links, TextureCraft.**

Photos (reported: empty gray boxes without SearXNG)
- Cause: place cards and timeline thumbnails searched SearXNG only, so without it they got no candidates.
- Keyless by default: Wikipedia + Wikimedia Commons (author · licence kept) → Openverse. `searxng_url` now defaults to empty.
- Optional broader coverage: SearXNG, Brave Search, Google Programmable Search, Pexels, Unsplash (`image_provider` picks the
  first; the rest stay as fallbacks). Keys are used server-side only and never appear in the card, the browser or tool output.
- An unreachable or failing provider is skipped for 5 minutes, so a missing SearXNG doesn't slow every card.
- A photo that can't be found shows a clean placeholder instead of a gray box.

Units (reported: °F/mph for an EU user)
- New `units` valve: `auto` (default, from each viewer's browser locale), `metric` or `imperial`, plus a per-user override.
  Weather and route distances follow it. Replaces `temperature_unit`.

Maps and routes (reported: pins but no route lines)
- Cause: single-day maps only drew a street route when the model added `"route": true`. Routes are now on by default
  (`"route": false` = pins only). Modes: walk, bike, drive, motorcycle.
- Router fallbacks (foot/bike → car, OSRM → FOSSGIS); the card and the model are told why when there is no route
  (service down, invalid coordinates, stops too far apart).
- Map apps menu: Google Maps, Apple Maps, OpenStreetMap, or download a GPX (OsmAnd, Organic Maps, Garmin). `map_app` picks the main button.
- No WebGL (blocklisted GPU, hardened Firefox profiles, VMs) or blocked map library: a static route sketch instead of a broken strip.

External links (reported: ERR_BLOCKED_BY_RESPONSE on desktop)
- Cause: Open WebUI's sandbox doesn't let popups escape it, and Google, Apple Maps and OpenStreetMap send
  Cross-Origin-Opener-Policy, so a tab opened from the card is blocked (switching map apps alone doesn't help).
- Links now open through the Open WebUI window when "iframe Sandbox Allow Same Origin" is on, directly on phones and tablets and for
  Open WebUI's own files, and otherwise copy the link and show a Copy / Try anyway sheet. The sandbox is not weakened.

Tool calls (reported: about half failed with malformed JSON)
- `spec` is now a JSON object parameter (a string still works), which avoids JSON-inside-a-string double escaping.
- Bounded repairs: code fences, prose around the object, smart quotes, trailing commas, raw newlines, truncation,
  double encoding, Python literals, a `{"spec": …}` wrapper, `components`/`sections` instead of `blocks`, common block-name slips.
- When it still can't be read, the model gets the position, a snippet and an example to fix it.
- Literal `\n` text from double-escaped output now becomes real line breaks (text, notes under the map, timeline).

Also
- **TextureCraft** (16th ArtCraft app): read GLB/glTF/FBX/DAE/USD/Alembic/OBJ/PLY and `.tcraft` projects with a rendered preview,
  edit with engine commands into a new `.tcraft`, convert a model to a project or export its textures.
- Regression tests: `tests/test_regressions.py` (no network) and `tests/test_browser.mjs` (Chromium, Firefox, WebKit).

Upgrading: if you use SearXNG, set `searxng_url` (it no longer defaults to `http://searxng:8080`). `temperature_unit` is replaced by `units`.

## 1.2.1 — 2026-11-01
- Fix: Download / Open note buttons now work (links are made absolute using your Open WebUI address).
- Self-hosted Craft web apps: serve precompressed .wasm (gzip_static) so WordCraft & co. load much faster.

## 1.2.0 — 2026-11-01
**Read and edit your own files with all 15 ArtCraft apps.**
- `craft_read` — open any attached file with its app and get its text, formulas, slides, structure and a preview card:
  WordCraft (docx/odt/rtf/md), GridCraft (xlsx/csv/ods, with formulas), DeckCraft (pptx), PdfCraft, PhotoCraft (png/jpg/psd/webp…),
  LightCraft (RAW), VectorCraft (svg/ai/eps), CADCraft (dxf/dwg), SolidCraft (step/stl/3mf), FigCraft (fig/sketch/penpot),
  DesignCraft (idml), SoundCraft (audio), FilmCraft (video), EffectCraft projects, and Craft Anything for everything else (zip, apps, binaries).
- `craft_edit` — headless edits into a new downloadable copy (originals are never touched): `replace_json` for documents,
  `cells_json` for spreadsheets, PDF page ops (rotate/delete/move/extract/combine), or any app engine command list.
- `craft_convert` — format conversion through the apps (docx↔pdf, pptx→pdf, xlsx↔csv, pdf→docx, psd→png, dxf→pdf, step→stl, wav→flac…).
- `craft_commands` — searchable command catalogue for every app.
- Added **SolidCraft** and **Craft Anything** to the desktop, the web apps and the `apps` launcher.
- Files are resolved from the chat's attachments; access is limited to the user's own files.

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
