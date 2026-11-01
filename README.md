# Intelligent WebUI

ChatGPT-style **Intelligent UI** for [Open WebUI](https://github.com/open-webui/open-webui). The model writes one small JSON
spec; the tool resolves **real photos, geocoded places and street routes** on the server and renders a polished, interactive
card inline in the chat.

- **Photo galleries** – three-up or scrolling, lightbox, captions. Images come from Wikipedia and your SearXNG; broken or
  icon-sized hits fall through to the next candidate automatically.
- **Live street maps** – MapLibre GL with OpenFreeMap vector tiles, numbered/emoji pins with decluttered labels, real
  walking routes inside a city (FOSSGIS OSRM foot) or driving routes for longer trips (OSRM), distance/time chip,
  group filter ("Morning / Afternoon"), fit and expand controls, raster fallback.
- **Linked itinerary** – timeline stops highlight and fly to their pin; clicking a pin highlights the stop.
- **Place cards** with photos, ratings, price, tags and links; **stats**, **bar/line charts**, **tables**, **compare**
  columns, **steps**, **callouts**, **hero** banner and **quotes**.
- **Citations** as favicon chips, a sources row, and **follow-up** suggestions that send the next prompt.
- Follows Open WebUI's light/dark theme live, reports its height, repairs fenced / truncated / trailing-comma JSON, and
  runs in a nonce-locked CSP sandbox.

| Block | Purpose |
|---|---|
| `text` | Markdown subset with `[1]` citation chips |
| `images` | Photo search queries → gallery |
| `map` | Places (name + best-guess lat/lng) → verified pins + street route |
| `places` | Photo cards for restaurants, hotels, products, people |
| `timeline` | Itinerary/history, linked to map places |
| `stats` · `chart` · `table` · `compare` · `steps` · `callout` · `hero` · `quote` | Everything else |

## Install

1. Open WebUI → **Workspace → Tools → +** and paste [`intelligent_ui.py`](intelligent_ui.py). Save (id `intelligent_ui`).
2. **Workspace → Models →** your model **→ Tools:** enable **Intelligent UI** (disable other generative-UI tools so the model
   has one clear choice). Native function calling works best.
3. Optional valves:

| Valve | Default | |
|---|---|---|
| `searxng_url` | `http://searxng:8080` | SearXNG with the JSON format enabled (image search). Leave as-is if you have none; Wikipedia still works. |
| `maplibre_cdn` | `https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1` | MapLibre GL JS package |
| `resolve_images` / `resolve_maps` | `true` | Turn server-side resolution off |

Requires Open WebUI ≥ 0.6 (tested on 0.12.5). The browser needs internet for map tiles and photos; the Open WebUI server
needs outbound HTTPS to Wikipedia, Photon/Nominatim (OSM), OSRM/FOSSGIS routing.

## Example spec

```json
{"title":"San Francisco in one day",
 "blocks":[
  {"type":"text","md":"I'd plan a **9 AM–7 PM route** along the waterfront [1]."},
  {"type":"images","items":[{"query":"Golden Gate Bridge from Baker Beach"},{"query":"Lombard Street"},{"query":"Palace of Fine Arts"}]},
  {"type":"map","area":"San Francisco, CA","route":true,"places":[
    {"name":"Ferry Building","lat":37.7955,"lng":-122.3937,"icon":"⛴️","group":"Morning","time":"9:00"},
    {"name":"Pier 39","lat":37.8087,"lng":-122.4098,"icon":"🦭","group":"Afternoon","time":"12:30"}]},
  {"type":"timeline","items":[{"time":"9:00 AM","title":"Ferry Building","place":"Ferry Building"}]}],
 "sources":[{"title":"Fleet Week schedule","url":"https://fleetweeksf.org/schedule/"}],
 "followups":["Make it a two-day itinerary"]}
```

Measured on a homelab: about 5 s to resolve 6 photo searches, 8 places and a walking route.

## Notes

- Open WebUI shows a tool result when it completes, so cards appear whole rather than streaming token by token.
- Public services have fair-use limits; the tool caches results, limits concurrency, backs off on HTTP 429 and falls back
  to the model's coordinates when geocoders are unavailable.

## Credits

Inspired by ChatGPT Intelligent UI and [thesysdev/open-intelligent-ui](https://github.com/thesysdev/open-intelligent-ui)
(MIT); the map palette and routing approach follow that project. Map data © OpenStreetMap contributors, tiles ©
OpenFreeMap / OpenMapTiles.

MIT License.
