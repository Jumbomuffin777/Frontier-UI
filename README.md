<div align="center">

# ✨ Frontier UI

**ChatGPT-style generative UI for [Open WebUI](https://github.com/open-webui/open-webui)** — real photos, live street maps with routes,
place cards, itineraries, charts and follow-ups, rendered right inside the chat.

<a href="https://buymeacoffee.com/jumbomuffin777"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="48"></a>

[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e.svg)](LICENSE)
[![Open WebUI](https://img.shields.io/badge/Open%20WebUI-%E2%89%A5%200.6-0ea5e9.svg)](https://github.com/open-webui/open-webui)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab.svg?logo=python&logoColor=white)](frontier_ui.py)
[![Single file](https://img.shields.io/badge/install-one%20file-a855f7.svg)](#-install)

<img src="docs/demo-restaurants.gif" alt="Frontier UI answering “good Italian restaurants in Downtown Chicago” with photo cards, sources and follow-ups" width="860">

**▶ [Watch the full demo video (2:40)](https://github.com/Jumbomuffin777/Frontier-UI/raw/main/docs/demo.mp4)**

</div>

---

## Why

Open WebUI answers in markdown. ChatGPT answers with an **interface**: photos of the places it mentions, a map with the route,
cards you can scroll, and next questions you can tap. Frontier UI brings that to any model in Open WebUI.

The model writes one small JSON spec. The tool does the rest on the server — **finds real photos, verifies places on the map
and draws real street routes** — then renders a polished, theme-aware card inline in the conversation.

<div align="center">
<img src="docs/demo-map.gif" alt="Follow-up question: walking distance from Union Station under $120 — live map with pins and restaurant cards" width="800">
<br><sub>Follow-up in the same chat: a live map around Union Station with pinned picks and photo cards.</sub>
<br><br>
<img src="docs/demo-trip.gif" alt="A seven-day Cancún plan: photos, currency tips, day tabs with a route per day on a self-hosted map, budget sliders, live weather, link previews and a spreadsheet export" width="600">
<br><sub>A 7-day Cancún trip: day-by-day routes on a self-hosted planet map, budget sliders, live weather, link previews — then “build me a spreadsheet”.</sub>
</div>

## ✨ Features

| | |
|---|---|
| 🖼️ **Photo galleries** | Real images from Wikipedia + your SearXNG, three-up or scrolling, captions and lightbox. Broken or icon-sized hits fall back to the next candidate automatically. |
| 🗺️ **Live street maps** | MapLibre GL + OpenFreeMap vector tiles, numbered / emoji pins with decluttered labels, **real walking routes** in a city (FOSSGIS) or driving routes for longer trips (OSRM), distance & time chip, group filter, fit & expand. |
| 🧭 **Linked itinerary** | Click a timeline stop and the map flies to its pin; click a pin and the stop lights up. |
| 🍝 **Place cards** | Photo, rating, price, neighborhood, tags and link — with sort and filter chips once there are four or more. |
| 📅 **Multi-day trips** | Day tabs with one coloured street route per day, **Open in Google Maps**, and **Add to calendar** (Google or `.ics`). |
| 💸 **Interactive tools** | Budget sliders with per-person totals and a cap, and calculators (mortgage, currency, anything) driven by safe formulas. |
| 📈 **Live data** | Weather forecasts and stock / crypto / FX quotes with 1D·1M·1Y charts — keyless, fetched at answer time. |
| 🔗 **Page previews** | Link cards with a real headless-Chromium screenshot, summary and reader view. |
| 📝 **Real Office files** | Export any card to Word, PDF, Excel or PowerPoint built by the open-source [Craft apps](https://github.com/storytold) — photos and charts included — and open it on a streamed Craft desktop. |
| ✉️ **Gmail & Notes** | Every card has Copy, Email (Gmail compose), Export and Save to Notes; `email` blocks become one-click Gmail drafts. |
| 📊 **Data blocks** | Stats tiles, bar & line charts, sortable tables, compare columns, steps, callouts, hero banner, quotes, status boards. |
| 🔗 **Citations & follow-ups** | Favicon citation chips, a sources row, and suggested next questions that send the prompt in one click. |
| 🌗 **Feels native** | Follows Open WebUI's light / dark theme live, auto-sizes, and runs in a nonce-locked CSP sandbox. |
| 🛟 **Forgiving** | Repairs fenced, truncated or trailing-comma JSON; caches lookups, limits concurrency and backs off on rate limits. |

## 🚀 Install

1. **Workspace → Tools → +** in Open WebUI, paste [`frontier_ui.py`](frontier_ui.py) and save.
2. **Workspace → Models →** your model **→ Tools:** enable **Frontier UI**. Turn off other generative-UI tools so the model
   has one clear choice. Native function calling works best.
3. Ask for something visual — *“Plan a day in San Francisco”*, *“Good Italian near Union Station under $120 for two”*,
   *“Compare the Arc Pro B70 and RTX 4090 for local LLMs”*.

### ⚙️ Valves

| Valve | Default | What it does |
|---|---|---|
| `searxng_url` | `http://searxng:8080` | SearXNG with the JSON format enabled, used for image search. Optional — Wikipedia still works without it. |
| `maplibre_cdn` | `https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1` | MapLibre GL JS package. |
| `resolve_images` / `resolve_maps` | `true` | Turn server-side photo or map resolution off. |
| `tiles_url` | *(empty)* | Self-hosted basemap folder (`planet.pmtiles`, `fonts/`, `sprites/`, `js/`) — see below. Empty = OpenFreeMap. |
| `live_data` · `temperature_unit` | `true` · `fahrenheit` | Live weather / quotes, and °F or °C. |
| `embedding_url` | `openwebui` | Reuse Open WebUI's embedding engine to rerank photos and match itinerary rows to pins; or an OpenAI-compatible URL (+ `embedding_model`, `embedding_api_key`); empty = off. |
| `craft_bridge_url` · `craft_bridge_token` | *(empty)* | The Craft bridge (real Office files, page screenshots). |
| `craft_desktop_url` · `craft_web_url` | *(empty)* | Links shown on file cards and in the `apps` launcher. |
| `page_screenshots` | `true` | Screenshots for link previews (needs the bridge). |

**Requirements:** Open WebUI ≥ 0.6 (tested on 0.12.5). Everything is keyless: the server needs outbound HTTPS to Wikipedia,
Photon / Nominatim, OSRM / FOSSGIS, Open-Meteo and Yahoo Finance; the browser loads map tiles and photos. The add-ons below are optional.

### 🏠 Optional self-hosted add-ons ([`server/`](server))

| Add-on | What you get | How |
|---|---|---|
| **Planet basemap** | Maps served from your own box — no tile API to break. ~140 GB; an HDD is fine. | [`server/local-web/setup.sh`](server/local-web/setup.sh) downloads the Protomaps planet, fonts and JS; nginx serves them with range requests. |
| **Craft desktop + bridge** | `craft_file` makes real `.docx/.xlsx/.pptx/.pdf` with WordCraft · GridCraft · DeckCraft, opens files in any of the 13 Craft apps, and takes page screenshots. | [`server/craft-apps`](server/craft-apps) — `linuxserver/craft-apps` plus [`bridge.py`](server/craft-bridge/bridge.py). **LAN only.** |
| **Craft web apps** | All 13 apps + the ArtCraft Launcher as static web apps for the `apps` block. | Same `setup.sh`, served under `/craft/`. |

### 🧰 Tool methods

| Method | Use |
|---|---|
| `render_frontier_ui(spec)` | The rich card. |
| `craft_file(format, card=…)` | Word / PDF / Excel / PowerPoint / CSV from a card (by id) or from Markdown, rows or slides. |
| `craft_open(url, app)` | Open a photo, PDF, SVG, audio or video in a Craft app on the desktop. |
| `save_note(card=…)` | Save a card or Markdown to Open WebUI Notes. |

## 🧩 How it works

```
model ──► render_frontier_ui(spec JSON)
            │
            ├─ photos   ─► Wikipedia + SearXNG   (ranked, deduplicated, cached)
            ├─ places   ─► Wikipedia coords / Photon / Nominatim  (snaps the model's estimate)
            ├─ routes   ─► FOSSGIS foot · OSRM car
            ▼
         sandboxed HTML card  ─►  MapLibre map · galleries · cards · charts · follow-ups
```

### Blocks

| Block | Purpose |
|---|---|
| `text` | Markdown subset with `[1]` citation chips |
| `images` | Photo search queries → gallery |
| `map` | Places (name + best-guess lat/lng) → verified pins + street route; `days` for multi-day trips |
| `places` | Photo cards for restaurants, hotels, products, people (sort + filter at 4+) |
| `timeline` | Itinerary or history, linked to map places; `date` enables Add to calendar |
| `budget` · `calculator` | Interactive sliders and formulas |
| `weather` · `stock` | Live forecast and quotes |
| `links` · `email` · `status` · `apps` | Page previews, Gmail drafts, health boards, Craft launcher |
| `stats` · `chart` · `table` · `compare` · `steps` · `callout` · `hero` · `quote` | Everything else |

<details>
<summary><b>Example spec</b></summary>

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

A full example lives in [`examples/san-francisco.py`](examples/san-francisco.py). On a homelab it resolves 6 photo searches,
8 places and a walking route in about 5 seconds.

</details>

## 🛠️ Development

The tool ships as one file, built from readable parts in [`src/`](src): `p1`, `p2`, `p6` are the Python resolvers,
`p3`–`p5` and `p7` the HTML / CSS / JS renderer, `p9` the tool class. See [`CHANGELOG.md`](CHANGELOG.md).

```bash
./src/build.sh   # rebuilds frontier_ui.py
```

## 📝 Notes

- Open WebUI shows a tool result when it completes, so cards appear whole rather than streaming token by token.
- Public map, routing and photo services have fair-use limits; results are cached and the tool falls back to the model's
  coordinates when geocoders are busy.

## 🙏 Credits

Inspired by ChatGPT's Intelligent UI and [thesysdev/open-intelligent-ui](https://github.com/thesysdev/open-intelligent-ui) (MIT),
whose map palette and routing approach this follows. Map data © OpenStreetMap contributors · tiles © OpenFreeMap / OpenMapTiles.

<div align="center">

**If Frontier UI made your chats nicer, consider buying me a coffee ☕**

<a href="https://buymeacoffee.com/jumbomuffin777"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="42"></a>

Released under the [MIT License](LICENSE).

</div>
