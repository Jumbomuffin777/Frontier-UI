---
name: generative-ui-widgets
description: "Use when answering travel/map/route questions: live photo-card + map + real-route widgets."
version: 2.0.1
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [widgets, travel, map, generative-ui, desktop]
    category: productivity
    related_skills: [hermes-desktop-plugins, tui-widgets]
---

# Generative UI Widgets (Frontier-UI port, v2)

ChatGPT-style generative UI built from free keyless public services, embedded in
Hermes chat via `::preview{file="..."}`. Ported from Frontier-UI (MIT,
Jumbomuffin777/Frontier-UI): map = MapLibre GL + OpenFreeMap vector tiles,
routing = public OSRM, photos = Wikipedia/Commons/SearXNG, geocoding =
Wiki coords -> Nominatim -> Photon. Ported blocks (vs upstream's 21): text,
images, map (multi-route day-tabs + GPX), places, timeline, budget, calculator,
weather, stock, table, compare, steps, callout, hero, quote, stats, status,
links, email, ics, sources, followups.

Rendering requires the Hermes desktop app (`::preview` is a desktop directive;
the TUI prints it literally). The pipeline itself is platform-neutral: on any
surface you can still build the widget HTML and hand the user its absolute path.

## When to Use
User asks for trip planning, place recommendations, walking/cycling/driving
routes, map visualization, or answers "like Frontier-UI would".

## Procedure

1. Write a spec JSON (v2 format, `blocks` array; upstream examples/ are a good
   reference):
   ```json
   {
     "title": "Two-day trip", "hint": "New Taipei City",
     "blocks": [
       {"type": "hero", "md": "..."},
       {"type": "map", "mode": "car", "hint": "New Taipei City",
        "stops": [{"name": "Old Cat Street", "page": "Old Cat Street", "day": "Day 1", "rating": 4.5, "tags": ["cat village"]}],
        "routes": [{"label": "Day 1", "mode": "car"}, {"label": "Day 2", "mode": "foot"}]},
       {"type": "timeline", "items": [{"time": "09:00", "title": "...", "place": "Old Cat Street", "day": "Day 1"}]},
       {"type": "budget", "items": [{"label": "Tickets", "cost": 90}], "cap": 500},
       {"type": "calculator", "expr": "p*r*i/(1-(1+i)**-n)", "vars": {"p": {"label": "Principal", "min": 0, "max": 10000000, "def": 5000000}}},
       {"type": "weather", "place": "Ruifang"},
       {"type": "stock", "symbols": [{"sym": "2330.TW"}, {"sym": "BTC-USD"}]},
       {"type": "table", "headers": ["Site", "Ticket"], "rows": [["Old Cat St", "free"]]},
       {"type": "email", "to": "...", "subject": "...", "body": "..."},
       {"type": "ics", "title": "...", "start": "20261121T0900", "end": "20261121T1100", "place": "Old Cat Street"}
     ],
     "sources": [{"title": "Wikipedia", "url": "https://..."}],
     "followups": ["rework as one-night-two-day"]
   }
   ```
   Rules: each stop's `day` must equal its `routes[i].label` (day-tabs link to
   them); timeline `place` must be byte-identical to a stop name (row click
   flashes the pin); `page` = Wikipedia article title (most reliable geocode
   source — always give it when the place name is ambiguous; for CJK names the
   article title often differs from the colloquial name); `hint` = city/country
   (drives Nominatim countrycodes).
2. Run the pipeline: `python3 scripts/build_widget.py spec.json out.html`
   (geocode -> OSRM -> weather/stock -> photos -> render; prints per-leg
   distance/time + geocode notes — reuse them verbatim in the text summary).
3. Verify rendering (see Verification), then deliver via
   `::preview{file="<absolute path to out.html>"}`.
4. Also give a text summary (distances/times/stop count/costs) — the widget is
   only the visual layer.
5. When the user clicks a widget button, its `data-hermes-send` text arrives as
   a user message; dispatch by content:
   - "Open this page in the preview browser: <url>" -> desktop_preview(open) + read back to confirm.
   - "Export ... as a GPX/ICS file..." -> write the .gpx/.ics from the coords in the message, deliver via MEDIA:.
   - "Draft this email with Gmail..." -> produce a mailto link or confirm content with the user.
   Followup button text should be written as a directly runnable rewrite instruction.

## Valves
- mode = foot|bike|car (OSRM routed-foot/bike/car). Multi-day trips use the routes array, one mode per route.
- Map style `tiles.openfreemap.org/styles/liberty`; switch to positron for a cleaner basemap.
- Photo priority: wiki summary -> local SearXNG if configured (spec `"searxng": "http://..."` or HERMES_SEARXNG env; SearXNG JSON API uses the `q=` param) -> Commons. Only hot-link-safe hosts pass (wikimedia/flickr/openverse/unsplash).
- stock = Yahoo Finance chart API (1D/1M/1Y SVG); weather = open-meteo.

## Pitfalls
- **Ambiguous place names**: Nominatim hits same-named places far away. `page`
  (wiki article) is the reliable fix; the script has a consensus repair (median
  clustering over all stops; outliers re-pick from candidates) but giving the
  right `page`/lat-lon in the spec is the real solution. Geocode failures raise
  an error telling you to add `page` or lat/lon.
- **CJK names**: TW_HINT (Taiwan place regex) and SUFFIX_TRIMS (Chinese generic
  suffixes like "old street"/"scenic area"/"station") exist purely to make CJK
  geocoding work — keep them; they are data, not prose. CJK tail-trim variants
  are tried progressively; the consensus cluster catches bad hits.
- **Sandbox dead links**: the `::preview` iframe is `sandbox="allow-scripts"` —
  `<a href>`, window.open, blob downloads, clipboard all fail silently; only
  data-hermes-send works. Every clickable element in the template emits a prompt.
- **JS braces**: never generate HTML/JS with f-string interpolation of braces;
  HTML is built with f-strings but the JS lives in templates/widget.html via
  `__TOKEN__` replacement.
- **node --check before delivery**: the script extracts the inline script and
  syntax-checks it; never deliver if it fails.
- **Fix the source, not the artifact**: text errors go in spec.json, re-run the
  pipeline; never hand-edit the HTML.
- **Script mixing in data strings**: wiki/OSM sources can mix simplified and
  traditional Chinese — scan strings before shipping to zh-TW users.
- **Public endpoint fair use**: OSRM/Nominatim are rate-limited; query once per
  widget build, cache results in scratch.
- **Widget size**: outer `.wrap` fixed at 760px; colors only via theme vars, no body background.
- **vision_analyze may 404**: verify rendering via DOM/network checks, not screenshots.
- **tab/timeline linkage**: stops.day == route.label and timeline.place == stop.name,
  exact case/spacing; mismatches make day-tab filtering miss rows (the script notes it).

## Verification
Open the file:// URL in the browser and check with js():
- `!!document.querySelector('#map canvas')` -> true; `.pin` count == stop count
- initial state: visible pins/tl rows == Day 1 stops/rows (day-tabs initial filter)
- switch tab -> pin count changes; click a timeline row -> `.pin.hi` == 1
- budget `.tot b` and calculator `.res b` show computed values; stock `svg.on` one per symbol
- photos naturalWidth>0; `performance.getEntriesByType('resource')` contains openfreemap and wikimedia

## Upstream sync
The canonical source of truth is `hermes-port/` in the Frontier-UI repo (a purely
additive directory; upstream files are never touched). `hermes-port/sync.sh`
installs it to the live Hermes skill at `~/.hermes/skills/generative-ui-widgets/`.
After upstream updates: git pull, diff src/, and only ever edit hermes-port/.
