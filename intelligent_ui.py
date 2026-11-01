"""
title: Intelligent UI
author: Zability (Claude Opus 5.5); inspired by ChatGPT Intelligent UI and thesysdev/open-intelligent-ui (MIT)
version: 1.0.0
description: ChatGPT-style Intelligent UI: real photo galleries, live street maps with numbered pins and routes, place cards, itineraries, charts, tables, citations and follow-ups. Media, places and routes are resolved server-side; rendering is an isolated embed.
required_open_webui_version: 0.6.0
"""
import asyncio
import json
import math
import re
import secrets
from urllib.parse import urlparse

import aiohttp
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse

UA = {"User-Agent": "zability-intelligent-ui/1.0 (self-hosted Open WebUI tool)"}
_IMG_CACHE: dict = {}
_GEO_CACHE: dict = {}
_ROUTE_CACHE: dict = {}
_SKIP_IMG = re.compile(r"\.svg|icon|logo|/map|_map|flag|seal|coat_of_arms|signature|diagram|sprite|avatar|placeholder", re.I)


def _cache_put(cache, key, value, cap=400):
    if len(cache) >= cap:
        cache.pop(next(iter(cache)))
    cache[key] = value


def _words(text):
    return {w for w in re.split(r"[^\w]+", (text or "").lower()) if len(w) > 3}


_SEMS: dict = {}


async def _get_json(session, url, params=None, timeout=6):
    """GET JSON with per-host politeness: Wikimedia gets 3 concurrent requests and backs off on 429."""
    host = url.split("/")[2]
    limit = 3 if "wiki" in host else 6
    loop = asyncio.get_running_loop()
    sem = _SEMS.get((host, id(loop)))
    if sem is None:
        sem = _SEMS[(host, id(loop))] = asyncio.Semaphore(limit)
    for attempt in range(3):
        async with sem:
            async with session.get(url, params=params, headers=UA, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                if r.status == 429 and attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                if r.status != 200:
                    raise RuntimeError(f"{url} {r.status}")
                return await r.json(content_type=None)
    raise RuntimeError(f"{url} 429")


async def _wiki_images(session, q):
    data = await _get_json(session, "https://en.wikipedia.org/w/api.php", {
        "action": "query", "format": "json", "formatversion": "2", "generator": "search", "gsrsearch": q,
        "gsrlimit": "5", "prop": "pageimages|info", "piprop": "thumbnail", "pithumbsize": "960", "inprop": "url"})
    wanted, out = _words(q), []
    for p in sorted((data.get("query") or {}).get("pages") or [], key=lambda p: p.get("index", 0)):
        src = (p.get("thumbnail") or {}).get("source")
        # only articles that are clearly ABOUT the query (most of its words in the title), e.g. not "Graphics card" for "Intel Arc graphics card"
        overlap = len(_words(p.get("title", "")) & wanted) / max(1, len(wanted))
        if src and not _SKIP_IMG.search(src) and (not wanted or overlap >= 0.6):
            out.append({"src": src, "page": p.get("fullurl", ""), "title": p.get("title", "")})
    return out


async def _searx_images(session, base, q):
    data = await _get_json(session, base.rstrip("/") + "/search", {"q": q, "categories": "images", "format": "json", "safesearch": "1"})
    out = []
    for r in (data.get("results") or [])[:12]:
        src = r.get("img_src") or ""
        if not src.startswith("https://") or _SKIP_IMG.search(src):
            continue
        out.append({"src": src, "page": r.get("url", ""), "title": r.get("title", "")})
    return out


async def _images_for(session, searx, q, wiki=True):
    q = re.sub(r"\s+", " ", str(q or "")).strip()[:160]
    if len(q) < 2:
        return []
    if q in _IMG_CACHE:
        return _IMG_CACHE[q]
    jobs = ([_wiki_images(session, q)] if wiki else []) + [_searx_images(session, searx, q)]
    res = await asyncio.gather(*jobs, return_exceptions=True)
    seen, out = set(), []
    for group in res:
        if isinstance(group, Exception):
            continue
        for it in group:
            if it["src"] not in seen:
                seen.add(it["src"])
                out.append(it)
    # photos first: transparent PNG cut-outs look empty as tiles, keep them as late fallbacks
    out = sorted(out, key=lambda it: 1 if re.search(r"\.png(\?|$)", it["src"], re.I) else 0)[:6]
    if out:
        _cache_put(_IMG_CACHE, q, out)
    return out


_PHOTON_SEM = None
_NOMI_LOCK = None


async def _geocode(session, q, bias=None):
    """Photon (2 concurrent, one retry), then Nominatim (serialized, 1 req/s per its policy)."""
    global _PHOTON_SEM, _NOMI_LOCK
    if _PHOTON_SEM is None:
        _PHOTON_SEM, _NOMI_LOCK = asyncio.Semaphore(2), asyncio.Lock()
    key = (q, None if not bias else (round(bias[0], 1), round(bias[1], 1)))
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]
    params = {"q": q, "limit": "1", "lang": "en"}
    if bias:
        params.update({"lat": f"{bias[0]:.4f}", "lon": f"{bias[1]:.4f}"})
    hit = None
    # 1) Wikipedia article coordinates: exact for landmarks, fast, tolerant of parallel requests
    name = q.split(",")[0].strip()
    want = {w for w in re.split(r"[^\w]+", name.lower()) if len(w) >= 2 and w not in ("the", "of", "and", "san", "st")}
    try:
        data = await _get_json(session, "https://en.wikipedia.org/w/api.php", {
            "action": "query", "format": "json", "formatversion": "2", "generator": "search", "gsrsearch": name,
            "gsrlimit": "5", "prop": "coordinates", "colimit": "max"}, timeout=4)
        for p in sorted((data.get("query") or {}).get("pages") or [], key=lambda p: p.get("index", 0)):
            c = (p.get("coordinates") or [None])[0]
            title_words = {w for w in re.split(r"[^\w]+", p.get("title", "").lower()) if len(w) >= 2}
            # the article must be ABOUT the place (title shares a word with the name), not the surrounding city
            if not c or (want and not (title_words & want)) or (bias and _km((c["lat"], c["lon"]), bias) >= 80):
                continue
            hit = (float(c["lat"]), float(c["lon"]))
            break
    except Exception:
        hit = None
    # 2) Photon (OSM) for shops, streets and anything without an article
    if hit is None:
        try:
            async with _PHOTON_SEM:
                data = await _get_json(session, "https://photon.komoot.io/api/", params, timeout=3)
            f = (data.get("features") or [None])[0]
            if f:
                lng, lat = f["geometry"]["coordinates"][:2]
                hit = (float(lat), float(lng))
        except Exception:
            hit = None
    if hit is None:
        try:
            async with _NOMI_LOCK:
                nparams = {"q": q, "format": "jsonv2", "limit": "1"}
                if bias:
                    nparams["viewbox"] = f"{bias[1]-0.5},{bias[0]+0.5},{bias[1]+0.5},{bias[0]-0.5}"
                data = await _get_json(session, "https://nominatim.openstreetmap.org/search", nparams, timeout=5)
                await asyncio.sleep(1.05)
            if data:
                hit = (float(data[0]["lat"]), float(data[0]["lon"]))
        except Exception:
            hit = None
    if hit:
        _cache_put(_GEO_CACHE, key, hit)
    return hit


def _km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


async def _route(session, pts, mode="auto"):
    """Street geometry in visiting order. City-scale stops use the FOSSGIS foot router (walkable paths, no
    detours over bridges), longer trips the OSRM car router."""
    spread = max(_km(pts[0], q) for q in pts)
    if mode == "auto":
        mode = "walk" if spread < 12 else "drive"
    key = (mode, tuple((round(a, 5), round(b, 5)) for a, b in pts))
    if key in _ROUTE_CACHE:
        return _ROUTE_CACHE[key]
    coords = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in pts)
    urls = ([f"https://routing.openstreetmap.de/routed-foot/route/v1/driving/{coords}"] if mode == "walk" else []) + \
           [f"https://router.project-osrm.org/route/v1/driving/{coords}"]
    data, used = None, mode
    for i, u in enumerate(urls):
        try:
            data = await _get_json(session, u, {"overview": "full", "geometries": "geojson", "steps": "false"}, timeout=6)
            if data.get("code") == "Ok" and data.get("routes"):
                used = mode if (mode == "drive" or i == 0) else "drive"
                break
        except Exception:
            data = None
    if not data or data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError("no route")
    r0 = data["routes"][0]
    out = {"line": [[c[1], c[0]] for c in r0["geometry"]["coordinates"]], "km": r0.get("distance", 0) / 1000.0,
           "min": r0.get("duration", 0) / 60.0, "mode": used}
    _cache_put(_ROUTE_CACHE, key, out, 200)
    return out


def _loads_lenient(spec):
    if isinstance(spec, (dict, list)):
        return spec
    s = str(spec or "").strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    s2 = re.sub(r",\s*([}\]])", r"\1", s)          # trailing commas
    s2 = re.sub(r"(?<!\\)'", '"', s2) if s2.count('"') < 2 else s2
    try:
        return json.loads(s2)
    except Exception:
        # truncated output: close open brackets
        stack, out, instr, esc = [], [], False, False
        for ch in s2:
            out.append(ch)
            if instr:
                esc = (ch == "\\" and not esc)
                if ch == '"' and not esc:
                    instr = False
                continue
            if ch == '"':
                instr = True
            elif ch in "[{":
                stack.append("]" if ch == "[" else "}")
            elif ch in "]}" and stack:
                stack.pop()
        tail = ('"' if instr else "") + "".join(reversed(stack))
        return json.loads(re.sub(r",\s*([}\]])", r"\1", "".join(out) + tail))


def _is_url(s):
    return isinstance(s, str) and s.startswith(("https://", "http://", "data:image/"))


async def _resolve(spec, searx, do_images=True, do_maps=True):
    """Fill photos, coordinates and street routes in place. Never raises; failures degrade gracefully."""
    blocks = spec.get("blocks") if isinstance(spec.get("blocks"), list) else []
    img_jobs = []  # (target dict, key, query)

    def want_img(obj, key, query, wiki=False):
        if do_images and isinstance(obj, dict) and query and not _is_url(obj.get(key)):
            img_jobs.append((obj, key, str(query), wiki))

    async with aiohttp.ClientSession() as session:
        geo_tasks = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            items = b.get("items") if isinstance(b.get("items"), list) else []
            if t == "images":
                if not items and isinstance(b.get("queries"), list):
                    items = b["items"] = [{"query": q} for q in b["queries"]]
                for it in items:
                    if isinstance(it, str):
                        it = {"query": it}
                    if isinstance(it, dict):
                        want_img(it, "candidates", it.get("query") or it.get("caption"), True)
                b["items"] = [it if isinstance(it, dict) else {"query": it} for it in items]
            elif t in ("places", "cards"):
                for it in items:
                    if isinstance(it, dict):
                        q = it.get("image") if isinstance(it.get("image"), str) and not _is_url(it.get("image")) else None
                        want_img(it, "candidates", q or " ".join(x for x in [it.get("name") or it.get("title"), b.get("area")] if x))
            elif t == "timeline":
                for it in items:
                    if isinstance(it, dict) and isinstance(it.get("image"), str) and not _is_url(it["image"]):
                        want_img(it, "candidates", it["image"])
            elif t == "hero":
                want_img(b, "candidates", b.get("image") if not _is_url(b.get("image")) else None, True)
            elif t == "map" and do_maps:
                geo_tasks.append(b)

        async def run_img(obj, key, q, wiki):
            try:
                obj[key] = await asyncio.wait_for(_images_for(session, searx, q, wiki), 6)
            except Exception:
                obj[key] = []

        async def run_map(b):
            places = [p for p in (b.get("places") or b.get("items") or []) if isinstance(p, dict)]
            b["places"] = places
            area = str(b.get("area") or spec.get("area") or "").strip()
            center = None
            if area:
                try:
                    center = await asyncio.wait_for(_geocode(session, area), 3)
                except Exception:
                    center = None

            async def one(p):
                name = str(p.get("query") or p.get("name") or "").strip()
                given = None
                try:
                    if p.get("lat") is not None and p.get("lng") is not None:
                        given = (float(p["lat"]), float(p["lng"]))
                        if not (-90 <= given[0] <= 90 and -180 <= given[1] <= 180):
                            given = None
                except Exception:
                    given = None
                hit = None
                if name:
                    q = name if (not area or area.lower() in name.lower()) else f"{name}, {area}"
                    try:
                        hit = await asyncio.wait_for(_geocode(session, q, given or center), 4.5)
                    except Exception:
                        hit = None
                # a geocoder hit refines the model's estimate; a far-away hit is a different place with the same name
                if hit and ((given and _km(hit, given) < 25) or (not given and (not center or _km(hit, center) < 80))):
                    p["lat"], p["lng"] = hit
                elif given and (not center or _km(given, center) < 150):
                    p["lat"], p["lng"] = given
                else:
                    p["lat"] = p["lng"] = None

            await asyncio.gather(*(one(p) for p in places), return_exceptions=True)
            pts = [(p["lat"], p["lng"]) for p in places if p.get("lat") is not None]
            if b.get("route") and 2 <= len(pts) <= 25 and max(_km(pts[0], q) for q in pts) < 400:
                try:
                    mode = str(b.get("mode") or "auto").lower()
                    b["route_geo"] = await _route(session, pts, mode if mode in ("walk", "drive") else "auto")
                except Exception:
                    b["route_geo"] = None

        await asyncio.gather(*(run_img(*j) for j in img_jobs), *(run_map(b) for b in geo_tasks), return_exceptions=True)
    return spec


def _safe_json(value):
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


async def _owui_theme(__event_call__):
    if not __event_call__:
        return "dark"
    try:
        r = await asyncio.wait_for(__event_call__({"type": "execute", "data": {"code": (
            "return (()=>{try{const s=localStorage.getItem('theme')||'';if(s.includes('dark')||s.includes('oled'))return 'dark';"
            "if(s==='light'||s==='her')return 'light';}catch(e){}const r=document.documentElement;"
            "if(r.classList.contains('dark'))return 'dark';if(r.classList.contains('light'))return 'light';"
            "return matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'})()")}}), 3)
        if isinstance(r, dict):
            r = r.get("result") or r.get("value") or r.get("data")
        return "dark" if "dark" in str(r).lower() else "light"
    except Exception:
        return "dark"


def _build_html(spec, theme, cdn):
    nonce = secrets.token_urlsafe(16)
    cdn = cdn.rstrip("/")
    host = "{0.scheme}://{0.netloc}".format(urlparse(cdn))
    html = _HTML.replace("__NONCE__", nonce).replace("__THEME__", "dark" if theme == "dark" else "light")
    html = html.replace("__CDN__", cdn).replace("__CDNHOST__", host).replace("__SPEC__", _safe_json(spec))
    return html


class Tools:
    """Intelligent UI: answer with a rich, ChatGPT-style visual card (photos, maps, places, itineraries, charts)."""

    class Valves(BaseModel):
        searxng_url: str = Field(default="http://searxng:8080", description="SearXNG base URL used for image search (JSON format enabled).")
        maplibre_cdn: str = Field(default="https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1", description="MapLibre GL JS package base URL.")
        resolve_images: bool = Field(default=True, description="Resolve photo queries to real images (Wikipedia + SearXNG).")
        resolve_maps: bool = Field(default=True, description="Geocode places (Photon/OSM) and draw street routes (OSRM).")

    def __init__(self):
        self.valves = self.Valves()

    async def render_intelligent_ui(self, spec: str, __event_emitter__=None, __event_call__=None) -> tuple:
        """
        Show a rich visual answer (ChatGPT-style Intelligent UI) inside the chat. Use it whenever the answer has places, trips,
        itineraries, products, people, comparisons, numbers, timelines or anything that reads better with photos, a map, cards,
        a table or a chart. You write ONE JSON object; the tool finds real photos, geocodes places, draws street routes and renders it.
        Never invent image URLs: give photo SEARCH QUERIES. For places give the real name plus your best lat/lng; the tool verifies them.
        After the tool returns, reply with 1-2 sentences only (the card already shows everything); do not repeat its content or the JSON.

        spec = {"title": str, "subtitle": str?, "sources": [{"title","url"}]?, "blocks": [Block...], "followups": [str, 2-4]}
        Blocks (use 3-7, in reading order; mix types, lead with text, put the most visual block early):
          {"type":"text","md":"markdown; **bold**, *italic*, [link](url), cite sources inline as [1] [2]"}
          {"type":"images","items":[{"query":"Golden Gate Bridge from Baker Beach","caption":"Golden Gate"}]}  (3 photos best; specific queries)
          {"type":"map","area":"San Francisco, CA","route":true,"places":[{"name":"Ferry Building","lat":37.7955,"lng":-122.3937,"icon":"⛴️","group":"Morning","note":"Coffee + market","time":"9:00"}]}
              (2-12 places in visiting order; lat/lng = your best estimate, the tool snaps them to the real place; route draws the
               street path; icon = one emoji; group optional e.g. Morning/Afternoon)
          {"type":"places","area":"San Francisco","items":[{"name","subtitle","rating":4.6,"price":"$$","tags":["Views"],"description","url"?,"image":"photo query"?}]}
          {"type":"timeline","items":[{"time":"9:00 AM","title","detail","place":"exact map place name"?}]}
          {"type":"table","columns":["A","B"],"rows":[["1","2"]]}
          {"type":"stats","items":[{"label","value","delta":"+4%"?,"tone":"up|down|neutral"?}]}
          {"type":"chart","kind":"bar|line","labels":["2023","2024"],"series":[{"name","data":[1,2]}],"unit":"%"?}
          {"type":"callout","tone":"info|tip|warning|danger","title","md"}
          {"type":"compare","items":[{"title","points":["..."],"verdict":"..."?}]}   (2-3 columns: options, pros/cons)
          {"type":"steps","items":[{"title","detail"}]}
          {"type":"hero","image":"photo query","eyebrow","title","md"}
          {"type":"quote","md","by"}
        Rules: concise, scannable copy; real facts only; cite with [n] only when sources are given; for trips always include
        images + map (route:true) + timeline whose "place" values match map place names exactly.

        :param spec: The JSON object described above (as a JSON string).
        :return: An interactive rich embed rendered inline in the chat.
        """
        try:
            data = _loads_lenient(spec)
        except Exception as e:
            return f"Intelligent UI could not parse spec JSON ({e}). Fix the JSON and call render_intelligent_ui again."
        if isinstance(data, list):
            data = {"blocks": data}
        if not isinstance(data, dict):
            return "Intelligent UI spec must be a JSON object with a blocks array."
        title = str(data.get("title") or "Response")[:120]
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Building “{title}”…", "done": False}})
        try:
            await asyncio.wait_for(_resolve(data, self.valves.searxng_url, self.valves.resolve_images, self.valves.resolve_maps), 12)
        except Exception:
            pass
        theme = await _owui_theme(__event_call__)
        resp = HTMLResponse(content=_build_html(data, theme, self.valves.maplibre_cdn), headers={"Content-Disposition": "inline"})
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Showing “{title}”", "done": True}})
        kinds = [b.get("type") for b in data.get("blocks", []) if isinstance(b, dict)]
        return resp, (f"Intelligent UI card “{title}” is rendered and visible to the user (blocks: {', '.join(map(str, kinds))}). "
                      "Reply with one or two short sentences that add context; do not repeat the card or show JSON.")


_HTML = r'''<!DOCTYPE html>
<html lang="en" data-theme="__THEME__" class="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-__NONCE__' __CDNHOST__; style-src 'unsafe-inline' __CDNHOST__; img-src https: http: data: blob:; connect-src https:; worker-src blob:; child-src blob:; font-src https: data:; base-uri 'none'; form-action 'none'">
<link rel="stylesheet" href="__CDN__/dist/maplibre-gl.css">
<style>
:root{--fg:#0d0d0d;--muted:#5d5d5d;--faint:#8f8f8f;--bg:transparent;--surface:#f4f4f5;--surface2:#ffffff;--line:rgba(0,0,0,.09);--accent:#0b6bcb;--ok:#15803d;--bad:#b91c1c;--warn:#b45309;--shadow:0 1px 2px rgba(0,0,0,.06),0 4px 14px rgba(0,0,0,.06);--route:#111;--routecase:#fff;--pin:#fff;--pinfg:#111;--chip:#ececee}
html.dark{--fg:#ececec;--muted:#a3a3a3;--faint:#7a7a7a;--surface:#232325;--surface2:#2b2b2e;--line:rgba(255,255,255,.09);--accent:#6cb4ff;--ok:#4ade80;--bad:#f87171;--warn:#fbbf24;--shadow:0 1px 2px rgba(0,0,0,.4),0 6px 18px rgba(0,0,0,.35);--route:#f2f2f2;--routecase:#1c1d1f;--pin:#1f2023;--pinfg:#f2f2f2;--chip:#333336}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:transparent;color:var(--fg);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
body{padding:2px 2px 6px;overflow:hidden}
#app{max-width:780px}
.blk{margin:0 0 18px;animation:rise .38s ease}
@keyframes rise{from{transform:translateY(5px)}to{transform:none}}
@media (prefers-reduced-motion:reduce){.blk{animation:none}}
h1.t{font-size:18px;font-weight:650;letter-spacing:-.01em;margin-bottom:4px}
.sub{color:var(--muted);font-size:14px;margin-bottom:14px}
.h2{font-size:15px;font-weight:620;margin:0 0 8px}
.prose p{margin:0 0 10px}.prose p:last-child{margin:0}
.prose strong{font-weight:640}.prose a{color:var(--accent);text-decoration:none}.prose a:hover{text-decoration:underline}
.prose ul,.prose ol{margin:4px 0 10px 20px}.prose li{margin:2px 0}
.prose code{font:13px ui-monospace,Menlo,monospace;background:var(--surface);padding:1px 5px;border-radius:5px}
.cite{display:inline-flex;align-items:center;gap:4px;vertical-align:1px;margin-left:3px;padding:1px 7px 1px 4px;border-radius:999px;background:var(--chip);color:var(--muted);font-size:11px;line-height:17px;cursor:pointer;white-space:nowrap;max-width:170px;overflow:hidden;text-overflow:ellipsis;border:0}
.cite img{width:12px;height:12px;border-radius:3px}
.cite:hover{color:var(--fg)}
/* images */
.gal{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.gal.n1{grid-template-columns:1fr}.gal.n2{grid-template-columns:1fr 1fr}
.gal.scroll{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none}.gal.scroll::-webkit-scrollbar{display:none}
.gal.scroll .ph{flex:0 0 calc(33.333% - 6px);scroll-snap-align:start}
.ph{position:relative;aspect-ratio:1.26;border-radius:14px;overflow:hidden;background:var(--surface);cursor:zoom-in}
.gal.n1 .ph{aspect-ratio:2}
.ph img{width:100%;height:100%;object-fit:cover;display:block;opacity:0;transition:opacity .35s,transform .5s}
.ph img.ok{opacity:1}.ph:hover img.ok{transform:scale(1.035)}
.ph .bm{position:absolute;top:8px;right:8px;width:26px;height:26px;border-radius:8px;background:rgba(0,0,0,.28);backdrop-filter:blur(6px);display:grid;place-items:center;color:#fff;opacity:.9}
.ph .cap{position:absolute;left:0;right:0;bottom:0;padding:18px 10px 8px;font-size:12px;color:#fff;background:linear-gradient(transparent,rgba(0,0,0,.55));opacity:0;transition:opacity .2s}
.ph:hover .cap{opacity:1}
.ph.miss{cursor:default;display:grid;place-items:center;text-align:center;padding:12px;color:var(--muted);font-size:13px;background:linear-gradient(135deg,var(--surface),var(--surface2))}
.shimmer{position:absolute;inset:0;background:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.08) 50%,transparent 70%);background-size:200% 100%;animation:sh 1.3s linear infinite}
html:not(.dark) .shimmer{background-image:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.6) 50%,transparent 70%)}
@keyframes sh{to{background-position:-200% 0}}
.wrap{position:relative}
.arrow{position:absolute;top:50%;transform:translateY(-50%);width:30px;height:30px;border-radius:50%;border:0;background:var(--surface2);color:var(--fg);box-shadow:var(--shadow);cursor:pointer;display:none;place-items:center;z-index:3}
.wrap:hover .arrow.on{display:grid}.arrow.l{left:-8px}.arrow.r{right:-8px}
/* lightbox */
.lb{position:fixed;inset:0;background:rgba(0,0,0,.82);display:flex;align-items:center;justify-content:center;z-index:50;flex-direction:column;gap:10px;padding:16px;cursor:zoom-out}
.lb img{max-width:100%;max-height:82%;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,.5)}
.lb .lbc{color:#ddd;font-size:13px;text-align:center}.lb a{color:#9cc9ff}
/* map */
.mapbox{position:relative;border-radius:16px;overflow:hidden;background:var(--surface);box-shadow:inset 0 0 0 1px var(--line);transition:height .35s ease}
.mapbox .maplibregl-map{position:absolute;inset:0}
.mctl{position:absolute;top:10px;z-index:4;display:flex;gap:6px}
.mctl.l{left:10px}.mctl.r{right:10px}
.mbtn{height:30px;padding:0 10px;border-radius:999px;border:0;background:var(--surface2);color:var(--fg);box-shadow:var(--shadow);font:12.5px/30px inherit;font-family:inherit;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.mbtn.ic{width:30px;padding:0;justify-content:center}
select.mbtn{appearance:none;padding-right:26px;background-image:linear-gradient(45deg,transparent 50%,currentColor 50%),linear-gradient(135deg,currentColor 50%,transparent 50%);background-position:calc(100% - 13px) 13px,calc(100% - 9px) 13px;background-size:4px 4px;background-repeat:no-repeat}
.mstat{position:absolute;left:10px;bottom:10px;z-index:4;font-size:12px;padding:5px 10px;border-radius:999px;background:var(--surface2);box-shadow:var(--shadow);color:var(--muted)}
.pin{display:flex;flex-direction:column;align-items:center;cursor:pointer;transition:opacity .2s}
.pin .dot{width:30px;height:30px;border-radius:50%;background:var(--pin);color:var(--pinfg);display:grid;place-items:center;font-size:15px;font-weight:650;box-shadow:0 1px 3px rgba(0,0,0,.25),0 0 0 2px var(--routecase);transition:transform .18s}
.pin .lab{margin-top:3px;font-size:11.5px;font-weight:600;color:var(--fg);white-space:nowrap;text-shadow:0 0 3px var(--routecase),0 0 3px var(--routecase),0 0 2px var(--routecase)}
.pin.sel .dot,.pin:hover .dot{transform:scale(1.18)}
.pin.sel .dot{background:var(--fg);color:var(--routecase)}
.pin.dim{opacity:.25}
.mpop{position:absolute;z-index:5;left:50%;bottom:12px;transform:translateX(-50%);max-width:88%;background:var(--surface2);border-radius:14px;box-shadow:var(--shadow);padding:10px 14px;font-size:13px;display:none}
.mpop b{display:block;font-size:14px}.mpop span{color:var(--muted)}
.maplibregl-ctrl-attrib{font-size:10px!important;background:transparent!important;opacity:.7}
html.dark .maplibregl-ctrl-attrib a{color:#aaa!important}
.maplist{display:flex;flex-wrap:wrap;gap:6px}
/* cards */
.cards{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none;padding:2px}
.cards::-webkit-scrollbar{display:none}
.card{flex:0 0 232px;scroll-snap-align:start;border-radius:16px;background:var(--surface);overflow:hidden;cursor:default;box-shadow:inset 0 0 0 1px var(--line);transition:transform .18s}
.card.link{cursor:pointer}.card.link:hover{transform:translateY(-2px)}
.card .ph{border-radius:0;aspect-ratio:1.45}
.card .cb{padding:10px 12px 12px}
.card .nm{font-weight:620;font-size:14.5px;line-height:1.3}
.card .meta{color:var(--muted);font-size:12.5px;margin-top:2px}
.card .ds{font-size:13px;margin-top:6px;color:var(--fg);opacity:.9;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px}
.tag{font-size:11px;padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--muted)}
.star{color:#f5a524}
/* timeline */
.tl{position:relative}
.ti{display:grid;grid-template-columns:74px 18px 1fr;gap:0 10px;padding:6px 6px;border-radius:12px;cursor:default}
.ti.go{cursor:pointer}.ti.go:hover,.ti.hl{background:var(--surface)}
.ti .tm{color:var(--muted);font-size:12.5px;text-align:right;padding-top:2px;font-variant-numeric:tabular-nums}
.ti .rail{position:relative;display:flex;justify-content:center}
.ti .rail:before{content:"";position:absolute;top:0;bottom:-12px;width:2px;background:var(--line)}
.ti:last-child .rail:before{bottom:50%}
.ti .bul{position:relative;margin-top:5px;width:12px;height:12px;border-radius:50%;background:var(--surface2);box-shadow:0 0 0 2px var(--fg)}
.ti .tt{font-weight:600;font-size:14.5px}
.ti .td{color:var(--muted);font-size:13.5px}
.ti .tbody{display:flex;gap:10px;align-items:flex-start}
.ti .thumb{flex:0 0 56px;height:56px;border-radius:10px;overflow:hidden;position:relative;background:var(--surface)}
.ti .thumb img{width:100%;height:100%;object-fit:cover}
/* table */
.tbl{overflow-x:auto;border-radius:14px;box-shadow:inset 0 0 0 1px var(--line)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{font-weight:560;color:var(--muted);text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);white-space:nowrap;font-size:12.5px}
td{padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}td:first-child{font-weight:560}
tbody tr:hover td{background:var(--surface)}
/* stats */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}
.st{background:var(--surface);border-radius:14px;padding:12px 14px}
.st .sl{color:var(--muted);font-size:12.5px}.st .sv{font-size:22px;font-weight:650;letter-spacing:-.01em;margin-top:2px}
.st .sd{font-size:12.5px;margin-top:2px}.up{color:var(--ok)}.down{color:var(--bad)}
/* chart */
.chart{background:var(--surface);border-radius:14px;padding:12px 12px 8px}
.chart svg{width:100%;height:auto;display:block;overflow:visible}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:2px 4px 6px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:5px;vertical-align:-1px}
/* callout */
.co{display:flex;gap:10px;padding:12px 14px;border-radius:14px;background:var(--surface);position:relative;overflow:hidden}
.co:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent)}
.co.warning:before{background:var(--warn)}.co.danger:before{background:var(--bad)}.co.tip:before{background:var(--ok)}
.co .ci{font-size:16px;line-height:22px}.co .ct{font-weight:620;font-size:14px;margin-bottom:2px}.co .prose{font-size:14px}
/* compare */
.cmp{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px}
.cmpc{background:var(--surface);border-radius:14px;padding:12px 14px;display:flex;flex-direction:column}
.cmpc .h{font-weight:620;margin-bottom:6px}
.cmpc ul{list-style:none;font-size:13.5px}.cmpc li{padding:3px 0 3px 20px;position:relative}
.cmpc li:before{content:"✓";position:absolute;left:2px;color:var(--ok);font-weight:700}
.cmpc li.neg:before{content:"–";color:var(--bad)}
.cmpc .v{margin-top:auto;padding-top:8px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
/* steps */
.steps{counter-reset:s}
.step{display:flex;gap:12px;padding:6px 0}
.step .n{flex:0 0 26px;height:26px;border-radius:50%;background:var(--fg);color:var(--routecase);display:grid;place-items:center;font-size:13px;font-weight:650}
.step .tt{font-weight:600}.step .td{color:var(--muted);font-size:13.5px}
/* hero */
.hero{position:relative;border-radius:18px;overflow:hidden;aspect-ratio:2.2;background:var(--surface)}
.hero .ph{position:absolute;inset:0;border-radius:0;aspect-ratio:auto;cursor:default}
.hero .ov{position:absolute;inset:0;background:linear-gradient(180deg,transparent 35%,rgba(0,0,0,.72));display:flex;flex-direction:column;justify-content:flex-end;padding:16px 18px;color:#fff}
.hero .eb{font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;opacity:.85}.hero .ht{font-size:22px;font-weight:680;letter-spacing:-.01em}.hero .prose{color:#eee;font-size:14px}
.quote{border-left:3px solid var(--fg);padding:4px 0 4px 14px;font-size:16px;font-style:italic}.quote .by{font-style:normal;color:var(--muted);font-size:13px;margin-top:4px}
/* sources + followups */
.srcs{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}
.src{flex:0 0 190px;background:var(--surface);border-radius:12px;padding:9px 11px;cursor:pointer;border:0;text-align:left;color:var(--fg);font-family:inherit}
.src:hover{background:var(--chip)}
.src .d{display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)}.src .d img{width:14px;height:14px;border-radius:3px}
.src .s{font-size:13px;margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.fu{display:flex;flex-direction:column}
.fu button{display:flex;align-items:center;gap:10px;width:100%;text-align:left;border:0;background:transparent;color:var(--fg);font:14px/1.4 inherit;font-family:inherit;padding:9px 6px;border-top:1px solid var(--line);cursor:pointer;border-radius:0}
.fu button:hover{background:var(--surface);border-radius:10px}
.fu button svg{flex:0 0 auto;color:var(--muted)}
.lbl{font-size:12.5px;color:var(--muted);font-weight:560;margin:0 0 6px;text-transform:none}
</style>
</head>
<body>
<div id="app"></div>
<script type="application/json" id="spec">__SPEC__</script>
'''

_HTML += r'''<script nonce="__NONCE__">
(function(){
"use strict";
var S={};try{S=JSON.parse(document.getElementById('spec').textContent)||{};}catch(e){S={blocks:[{type:'text',md:'Could not read the UI spec.'}]};}
var app=document.getElementById('app');
/* ---------- parent bridge ---------- */
var origin='*';try{if(document.referrer)origin=new URL(document.referrer).origin;}catch(e){}
function post(m){try{parent.postMessage(m,origin);}catch(e){}}
function sendPrompt(t){post({type:'input:prompt:submit',text:String(t)});}
function openLink(u){try{var p=new URL(String(u||''),location.href);if(!/^https?:$/.test(p.protocol))return;var w=null;try{w=parent.window.open(p.href,'_blank','noopener,noreferrer');}catch(e){w=window.open(p.href,'_blank','noopener,noreferrer');}if(w)w.opener=null;}catch(e){}}
var lastH=0,raf=0;
function reportHeight(){var h=Math.ceil(Math.max(document.body.scrollHeight,document.documentElement.scrollHeight));if(Math.abs(h-lastH)<2)return;lastH=h;post({type:'iframe:height',height:h});}
function schedule(){cancelAnimationFrame(raf);raf=requestAnimationFrame(reportHeight);}
new ResizeObserver(schedule).observe(document.body);
window.addEventListener('load',function(){reportHeight();setTimeout(reportHeight,300);setTimeout(reportHeight,1500);});
/* ---------- theme follow ---------- */
function applyTheme(dark){var r=document.documentElement;r.classList.toggle('dark',dark);r.classList.toggle('light',!dark);r.setAttribute('data-theme',dark?'dark':'light');document.dispatchEvent(new Event('iui-theme'));}
try{var pr=parent.document.documentElement;var det=function(){var s='';try{s=parent.localStorage.getItem('theme')||'';}catch(e){}if(s.indexOf('dark')>=0||s.indexOf('oled')>=0)return true;if(s==='light'||s==='her')return false;return pr.classList.contains('dark');};
applyTheme(det());new MutationObserver(function(){applyTheme(det());}).observe(pr,{attributes:true,attributeFilter:['class']});}catch(e){}
function isDark(){return document.documentElement.classList.contains('dark');}
/* ---------- helpers ---------- */
function h(tag,cls,kids){var e=document.createElement(tag);if(cls)e.className=cls;(kids||[]).forEach(function(k){if(k==null)return;e.appendChild(typeof k==='string'?document.createTextNode(k):k);});return e;}
function txt(tag,cls,t){var e=h(tag,cls);e.textContent=t==null?'':String(t);return e;}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function arr(x){return Array.isArray(x)?x:[];}
function domain(u){try{return new URL(u).hostname.replace(/^www\./,'');}catch(e){return '';}}
function fav(u){var d=domain(u);return d?'https://icons.duckduckgo.com/ip3/'+d+'.ico':'';}
var SRC=arr(S.sources).map(function(s){return typeof s==='string'?{url:s,title:domain(s)}:(s||{});}).filter(function(s){return s.url;});
var SVG={
 bm:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h12v18l-6-4-6 4z"/></svg>',
 arrow:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
 l:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M15 6l-6 6 6 6"/></svg>',
 r:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>',
 exp:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
 col:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>',
 nav:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"><path d="M3 11l18-8-8 18-2-8z"/></svg>',
 fit:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8"/></svg>'};
function icon(name){var s=document.createElement('span');s.style.display='inline-flex';s.innerHTML=SVG[name];return s;}
/* inline markdown: escape first, then a safe subset */
function inl(s){
 s=esc(s);
 s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
 s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/(^|[^*])\*([^*\n]+)\*/g,'$1<em>$2</em>');
 s=s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,function(m,t,u){return '<a href="#" data-url="'+u+'">'+t+'</a>';});
 s=s.replace(/\[(\d{1,2})\]/g,function(m,n){var src=SRC[+n-1];if(!src)return '';var d=domain(src.url);var more='';return '<button class="cite" data-url="'+esc(src.url)+'" title="'+esc(src.title||d)+'"><img src="'+esc(fav(src.url))+'" alt="" onerror="this.remove()">'+esc(d)+'</button>';});
 return s;}
function md(src){
 var out=[],list=null,lines=String(src||'').split(/\n/);
 lines.forEach(function(l){var m=l.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/);
  if(m){var tag=m[1]?'ol':'ul';if(!list||list.tag!==tag){if(list)out.push('</'+list.tag+'>');list={tag:tag};out.push('<'+tag+'>');}out.push('<li>'+inl(m[2])+'</li>');return;}
  if(list){out.push('</'+list.tag+'>');list=null;}
  if(l.trim()){var hm=l.match(/^#{1,4}\s+(.*)$/);out.push(hm?'<p><strong>'+inl(hm[1])+'</strong></p>':'<p>'+inl(l)+'</p>');}});
 if(list)out.push('</'+list.tag+'>');
 var d=h('div','prose');d.innerHTML=out.join('');return d;}
document.addEventListener('click',function(e){var a=e.target.closest('[data-url]');if(a){e.preventDefault();openLink(a.getAttribute('data-url'));}});
/* photos with candidate fallback */
function photo(item,cls,opts){
 opts=opts||{};var box=h('div','ph'+(cls?' '+cls:''));var c=arr(item&&item.candidates);
 if(item&&typeof item.image==='string'&&/^https:/.test(item.image))c=[{src:item.image}].concat(c);
 if(item&&typeof item.src==='string'&&/^https:/.test(item.src))c=[{src:item.src}].concat(c);
 var cap=(item&&(item.caption||item.name||item.title||item.query))||'';
 if(!c.length){box.classList.add('miss');box.textContent=opts.noText?'':cap;return box;}
 var sh=h('div','shimmer');box.appendChild(sh);var img=document.createElement('img');img.alt=cap;img.loading='lazy';img.referrerPolicy='no-referrer';var i=0;
 function next(){if(i>=c.length){box.classList.add('miss');img.remove();sh.remove();box.textContent=opts.noText?'':cap;return;}img.src=c[i++].src;}
 img.onload=function(){if(img.naturalWidth<140&&i<c.length){next();return;}img.classList.add('ok');sh.remove();box.dataset.page=(c[i-1]&&c[i-1].page)||'';};
 img.onerror=next;next();box.appendChild(img);
 if(opts.bookmark){var b=h('div','bm');b.innerHTML=SVG.bm;box.appendChild(b);}
 if(opts.caption&&cap){box.appendChild(txt('div','cap',cap));}
 if(opts.zoom){box.addEventListener('click',function(){if(img.classList.contains('ok'))lightbox(img.src,cap,box.dataset.page);});}
 return box;}
function lightbox(src,cap,page){var lb=h('div','lb');var im=document.createElement('img');im.src=src;lb.appendChild(im);var c=h('div','lbc');c.appendChild(document.createTextNode(cap||''));if(page){c.appendChild(document.createTextNode('  ·  '));var a=txt('a','',domain(page));a.href='#';a.setAttribute('data-url',page);c.appendChild(a);}lb.appendChild(c);lb.addEventListener('click',function(e){if(!e.target.closest('a'))lb.remove();});document.body.appendChild(lb);}
function scroller(inner){var w=h('div','wrap',[inner]);var L=h('button','arrow l');L.innerHTML=SVG.l;var R=h('button','arrow r');R.innerHTML=SVG.r;w.appendChild(L);w.appendChild(R);
 function upd(){L.classList.toggle('on',inner.scrollLeft>4);R.classList.toggle('on',inner.scrollLeft+inner.clientWidth<inner.scrollWidth-4);}
 L.onclick=function(){inner.scrollBy({left:-inner.clientWidth*.8,behavior:'smooth'});};R.onclick=function(){inner.scrollBy({left:inner.clientWidth*.8,behavior:'smooth'});};
 inner.addEventListener('scroll',upd);setTimeout(upd,100);window.addEventListener('resize',upd);return w;}
function label(t){return t?txt('div','h2',t):null;}
'''

_HTML += r'''window.IUI={S:S,app:app,SRC:SRC,h:h,txt:txt,arr:arr,md:md,photo:photo,scroller:scroller,label:label,icon:icon,SVG:SVG,isDark:isDark,openLink:openLink,sendPrompt:sendPrompt,reportHeight:reportHeight,fav:fav,domain:domain,CDN:'__CDN__',NONCE:'__NONCE__'};
})();
</script>
'''
_HTML = _HTML.replace(' onerror="this.remove()"', '').replace(
    ".ti .thumb img{width:100%;height:100%;object-fit:cover}",
    ".ti .thumb img{width:100%;height:100%;object-fit:cover}.ti .thumb .ph{aspect-ratio:auto;height:100%;border-radius:0}")

_HTML += r'''<script nonce="__NONCE__">
(function(){
"use strict";
var I=window.IUI;
var h=I.h,txt=I.txt,arr=I.arr,md=I.md,photo=I.photo,scroller=I.scroller,label=I.label,icon=I.icon,SVG=I.SVG;
var MAPS=[];/* registry: {places, select(name)} */
function findPlace(name){name=String(name||'').toLowerCase().trim();if(!name)return null;for(var i=0;i<MAPS.length;i++){var m=MAPS[i];for(var j=0;j<m.places.length;j++){var p=m.places[j];var n=String(p.name||'').toLowerCase();if(n===name||n.indexOf(name)>=0||name.indexOf(n)>=0)return {map:m,idx:j};}}return null;}
/* ---------- maplibre loader ---------- */
var libP=null;
function loadLib(){if(window.maplibregl)return Promise.resolve(window.maplibregl);if(libP)return libP;libP=new Promise(function(res,rej){var s=document.createElement('script');s.src=I.CDN+'/dist/maplibre-gl.js';s.nonce=I.NONCE;s.onload=function(){window.maplibregl?res(window.maplibregl):rej(new Error('maplibre missing'));};s.onerror=rej;document.head.appendChild(s);});return libP;}
var PAL={light:{bg:'#f4f2f0',green:'#bce9b0',park:'#b7e7aa',campus:'#ede8d7',water:'#a2dff5',waterway:'#91d6ef',building:'#e9e6e2',street:'#d6d9df',road:'#b9c0cc',ferry:'#89cfe9',label:'#50545a',minor:'#687078',halo:'#ffffff'},
 dark:{bg:'#1c1d1f',green:'#1f2b22',park:'#20301f',campus:'#26241f',water:'#1d3540',waterway:'#23414d',building:'#28292b',street:'#36393e',road:'#4b5058',ferry:'#2b5566',label:'#b4b9bf',minor:'#8d939a',halo:'#1c1d1f'}};
function vstyle(dark){var c=dark?PAL.dark:PAL.light;var name=['coalesce',['get','name_en'],['get','name']];
 return {version:8,glyphs:'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
 sources:{p:{type:'vector',url:'https://tiles.openfreemap.org/planet',attribution:'© OpenFreeMap © OpenMapTiles © OpenStreetMap'}},
 layers:[{id:'bg',type:'background',paint:{'background-color':c.bg}},
 {id:'lc',type:'fill',source:'p','source-layer':'landcover',filter:['in','class','wood','grass'],paint:{'fill-color':c.green,'fill-opacity':.8}},
 {id:'park',type:'fill',source:'p','source-layer':'park',paint:{'fill-color':c.park}},
 {id:'lu',type:'fill',source:'p','source-layer':'landuse',filter:['in','class','school','university','hospital'],paint:{'fill-color':c.campus}},
 {id:'water',type:'fill',source:'p','source-layer':'water',paint:{'fill-color':c.water}},
 {id:'ww',type:'line',source:'p','source-layer':'waterway',paint:{'line-color':c.waterway,'line-width':1}},
 {id:'bld',type:'fill',minzoom:14,source:'p','source-layer':'building',paint:{'fill-color':c.building}},
 {id:'st',type:'line',source:'p','source-layer':'transportation',filter:['!in','class','rail','transit','ferry','motorway','trunk','primary'],layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':c.street,'line-width':['interpolate',['linear'],['zoom'],9,.3,12,1.5,14,2.8,17,8]}},
 {id:'rd',type:'line',source:'p','source-layer':'transportation',filter:['in','class','motorway','trunk','primary'],layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':c.road,'line-width':['interpolate',['linear'],['zoom'],9,.7,12,3,14,5,17,12]}},
 {id:'fe',type:'line',source:'p','source-layer':'transportation',filter:['==','class','ferry'],paint:{'line-color':c.ferry,'line-width':.8}},
 {id:'nb',type:'symbol',source:'p','source-layer':'place',minzoom:10,maxzoom:15,filter:['in','class','suburb','quarter','neighbourhood'],layout:{'text-field':name,'text-font':['Noto Sans Regular'],'text-size':10,'text-letter-spacing':.08,'text-transform':'uppercase','text-max-width':8},paint:{'text-color':c.minor,'text-halo-color':c.halo,'text-halo-width':1.2}},
 {id:'city',type:'symbol',source:'p','source-layer':'place',minzoom:5,maxzoom:13,filter:['in','class','city','town'],layout:{'text-field':name,'text-font':['Noto Sans Regular'],'text-size':14,'text-max-width':8},paint:{'text-color':c.label,'text-halo-color':c.halo,'text-halo-width':1.5}}]};}
function rstyle(dark){return {version:8,sources:{r:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/'+(dark?'Canvas/World_Dark_Gray_Base':'World_Street_Map')+'/MapServer/tile/{z}/{y}/{x}'],tileSize:256,maxzoom:19,attribution:'Tiles © Esri · © OpenStreetMap'}},layers:[{id:'r',type:'raster',source:'r'}]};}
function fmtKm(km){return km<10?km.toFixed(1)+' km':Math.round(km)+' km';}
function fmtMin(m){m=Math.round(m);return m<60?m+' min':Math.floor(m/60)+' h '+(m%60?m%60+' min':'');}
function mapBlock(b){
 var places=arr(b.places).filter(function(p){return p&&p.lat!=null&&p.lng!=null&&isFinite(p.lat)&&isFinite(p.lng);});
 var wrap=h('div','blk');if(b.title)wrap.appendChild(label(b.title));
 if(!places.length){var l=h('div','maplist');arr(b.places).forEach(function(p){l.appendChild(txt('span','tag',(p.icon?p.icon+' ':'')+(p.name||'')));});wrap.appendChild(l);return wrap;}
 var base=Math.min(560,Math.max(240,+b.height||380));var box=h('div','mapbox');box.style.height=base+'px';wrap.appendChild(box);
 var groups=[];places.forEach(function(p){if(p.group&&groups.indexOf(p.group)<0)groups.push(p.group);});
 var ctlL=h('div','mctl l'),ctlR=h('div','mctl r');box.appendChild(ctlL);box.appendChild(ctlR);
 var sel=null;if(groups.length>1){sel=document.createElement('select');sel.className='mbtn';var o=document.createElement('option');o.value='';o.textContent='All groups';sel.appendChild(o);groups.forEach(function(g){var oo=document.createElement('option');oo.value=g;oo.textContent=g;sel.appendChild(oo);});ctlL.appendChild(sel);}
 var bFit=h('button','mbtn ic',[icon('nav')]);bFit.title='Fit all places';ctlL.appendChild(bFit);
 var bExp=h('button','mbtn',[icon('exp'),txt('span','','Expand')]);ctlR.appendChild(bExp);
 var pop=h('div','mpop');box.appendChild(pop);
 var rg=b.route_geo;if(rg&&rg.km){box.appendChild(txt('div','mstat',(rg.mode==='walk'?'🚶 ':'🚗 ')+fmtKm(rg.km)+' · '+fmtMin(rg.min)+(rg.mode==='walk'?' walking':' by car')+' · '+places.length+' stops'));}
 var reg={places:places,select:function(){}};MAPS.push(reg);
 loadLib().then(function(lib){
  var dark=I.isDark();var usedRaster=false;
  var map=new lib.Map({container:box,style:vstyle(dark),attributionControl:{compact:true},dragRotate:false,pitchWithRotate:false,cooperativeGestures:false,fadeDuration:150});
  map.scrollZoom.disable();box.addEventListener('wheel',function(e){if(e.ctrlKey||e.metaKey){map.scrollZoom.enable();}else{map.scrollZoom.disable();}},{passive:true});
  var failT=setTimeout(function(){if(!map.isStyleLoaded()&&!usedRaster){usedRaster=true;map.setStyle(rstyle(I.isDark()));}},7000);
  map.on('error',function(){if(!usedRaster&&!map.isStyleLoaded()){usedRaster=true;map.setStyle(rstyle(I.isDark()));}});
  var line=(rg&&rg.line&&rg.line.length>1)?rg.line:(b.route?places.map(function(p){return [p.lat,p.lng];}):null);
  function addRoute(){if(!line||map.getSource('route'))return;var gj={type:'Feature',geometry:{type:'LineString',coordinates:line.map(function(c){return [c[1],c[0]];})}};
   map.addSource('route',{type:'geojson',data:gj});
   map.addLayer({id:'route-case',type:'line',source:'route',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':getComputedStyle(document.documentElement).getPropertyValue('--routecase').trim()||'#fff','line-width':7,'line-opacity':.95}});
   map.addLayer({id:'route',type:'line',source:'route',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':getComputedStyle(document.documentElement).getPropertyValue('--route').trim()||'#111','line-width':3.6,'line-dasharray':(rg&&rg.line)?[1,0]:[1.5,1.5]}});}
  map.on('styledata',function(){if(map.isStyleLoaded()){clearTimeout(failT);addRoute();}});
  map.on('load',addRoute);
  var mk=[];
  places.forEach(function(p,i){var el=h('div','pin');var dot=txt('div','dot',p.icon||String(i+1));var lab=txt('div','lab',p.name||'');el.appendChild(dot);el.appendChild(lab);
   el.addEventListener('click',function(e){e.stopPropagation();choose(i,true);});
   var m=new lib.Marker({element:el,anchor:'top',offset:[0,-15]}).setLngLat([p.lng,p.lat]).addTo(map);mk.push({m:m,el:el,p:p});});
  function bounds(list){var bb=new lib.LngLatBounds();list.forEach(function(p){bb.extend([p.lng,p.lat]);});if(line&&!(sel&&sel.value))line.forEach(function(c){bb.extend([c[1],c[0]]);});return bb;}
  function fit(list,anim){if(!list.length)return;if(list.length===1){map.jumpTo({center:[list[0].lng,list[0].lat],zoom:14});return;}map.fitBounds(bounds(list),{padding:{top:56,bottom:48,left:44,right:44},maxZoom:15,duration:anim?600:0});}
  fit(places,false);
  var cur=-1;
  /* label decluttering: greedily hide labels that would overlap an earlier (or the selected) one */
  function declutter(){var placed=[];var order=mk.map(function(o,j){return j;});if(cur>=0){order.splice(order.indexOf(cur),1);order.unshift(cur);}
   order.forEach(function(j){var o=mk[j];var pt=map.project([o.p.lng,o.p.lat]);var w=Math.min(220,(o.p.name||'').length*6.6+8);var r={x0:pt.x-w/2,x1:pt.x+w/2,y0:pt.y+2,y1:pt.y+20};var dot={x0:pt.x-15,x1:pt.x+15,y0:pt.y-15,y1:pt.y+15};
    var hit=placed.some(function(q){return !(r.x1<q.x0||r.x0>q.x1||r.y1<q.y0||r.y0>q.y1);});
    o.el.querySelector('.lab').style.visibility=hit?'hidden':'visible';placed.push(dot);if(!hit)placed.push(r);});}
  map.on('moveend',declutter);map.once('idle',declutter);setTimeout(declutter,50);
  function choose(i,fly){cur=i;mk.forEach(function(o,j){o.el.classList.toggle('sel',j===i);});var p=places[i];
   pop.innerHTML='';pop.appendChild(txt('b','',(p.icon?p.icon+'  ':'')+(p.name||'')));var meta=[p.time,p.note].filter(Boolean).join(' · ');if(meta)pop.appendChild(txt('span','',meta));pop.style.display='block';
   if(fly)map.easeTo({center:[p.lng,p.lat],zoom:Math.max(map.getZoom(),14),duration:600});
   declutter();document.dispatchEvent(new CustomEvent('iui-place',{detail:{name:p.name}}));}
  reg.select=function(i){choose(i,true);box.scrollIntoView({block:'nearest',behavior:'smooth'});};
  map.on('click',function(){cur=-1;pop.style.display='none';mk.forEach(function(o){o.el.classList.remove('sel');});});
  bFit.onclick=function(){fit(sel&&sel.value?places.filter(function(p){return p.group===sel.value;}):places,true);};
  if(sel)sel.onchange=function(){var g=sel.value;mk.forEach(function(o){o.el.classList.toggle('dim',!!g&&o.p.group!==g);});fit(g?places.filter(function(p){return p.group===g;}):places,true);};
  var big=false;bExp.onclick=function(){big=!big;box.style.height=(big?Math.max(560,Math.round(base*1.7)):base)+'px';bExp.innerHTML='';bExp.appendChild(icon(big?'col':'exp'));bExp.appendChild(txt('span','',big?'Collapse':'Expand'));setTimeout(function(){map.resize();fit(places,true);},380);};
  document.addEventListener('iui-theme',function(){usedRaster=false;map.setStyle(vstyle(I.isDark()));});
  new ResizeObserver(function(){map.resize();}).observe(box);
 }).catch(function(){box.style.height='auto';box.style.padding='12px';var l=h('div','maplist');places.forEach(function(p,i){l.appendChild(txt('span','tag',(p.icon||(i+1)+'.')+' '+p.name));});box.appendChild(l);});
 return wrap;}
/* ---------- other blocks ---------- */
function images(b){var it=arr(b.items).slice(0,9);var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','gal'+(it.length>3?' scroll':' n'+it.length));
 it.forEach(function(x){g.appendChild(photo(x,'',{bookmark:true,caption:true,zoom:true}));});w.appendChild(it.length>3?scroller(g):g);return w;}
function stars(r){r=+r;if(!isFinite(r))return null;var s=h('span','');s.appendChild(txt('span','star','★ '));s.appendChild(document.createTextNode(r.toFixed(1)));return s;}
function places(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var row=h('div','cards');
 arr(b.items).forEach(function(it){if(!it)return;var c=h('div','card'+(it.url?' link':''));c.appendChild(photo(it,'',{noText:true}));var cb=h('div','cb');cb.appendChild(txt('div','nm',it.name||it.title||''));
  var meta=h('div','meta');var bits=[];var st=stars(it.rating);if(st)bits.push(st);[it.price,it.subtitle].forEach(function(x){if(x)bits.push(document.createTextNode(String(x)));});
  bits.forEach(function(x,i){if(i)meta.appendChild(document.createTextNode(' · '));meta.appendChild(x);});if(bits.length)cb.appendChild(meta);
  if(it.description)cb.appendChild(txt('div','ds',it.description));
  var tg=arr(it.tags).slice(0,3);if(tg.length){var t=h('div','tags');tg.forEach(function(x){t.appendChild(txt('span','tag',x));});cb.appendChild(t);}
  c.appendChild(cb);if(it.url)c.addEventListener('click',function(){I.openLink(it.url);});
  c.addEventListener('mouseenter',function(){var f=findPlace(it.name);if(f)f.map.select&&0;});
  row.appendChild(c);});
 w.appendChild(scroller(row));return w;}
function timeline(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var tl=h('div','tl');
 arr(b.items).forEach(function(it){if(!it)return;var f=findPlace(it.place||it.title);var row=h('div','ti'+(f?' go':''));row.appendChild(txt('div','tm',it.time||''));var rail=h('div','rail',[h('div','bul')]);row.appendChild(rail);
  var body=h('div','tbody');if(it.candidates&&it.candidates.length){var th=h('div','thumb');th.appendChild(photo(it,'',{noText:true}));body.appendChild(th);}
  var tx=h('div','');tx.appendChild(txt('div','tt',it.title||''));if(it.detail)tx.appendChild(txt('div','td',it.detail));body.appendChild(tx);row.appendChild(body);
  if(f){row.addEventListener('click',function(){f.map.select(f.idx);});row.dataset.place=String(f.map.places[f.idx].name||'').toLowerCase();}
  tl.appendChild(row);});
 document.addEventListener('iui-place',function(e){var n=String(e.detail.name||'').toLowerCase();tl.querySelectorAll('.ti').forEach(function(r){r.classList.toggle('hl',!!n&&r.dataset.place===n);});});
 w.appendChild(tl);return w;}
function table(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var t=h('table');var th=h('thead'),tr=h('tr');arr(b.columns).forEach(function(c){tr.appendChild(txt('th','',c));});th.appendChild(tr);t.appendChild(th);
 var tb=h('tbody');arr(b.rows).forEach(function(r){var row=h('tr');arr(r).forEach(function(c){var td=h('td');td.appendChild(md(c).firstChild||document.createTextNode(''));if(td.firstChild&&td.firstChild.tagName==='P'){td.innerHTML=td.firstChild.innerHTML;}row.appendChild(td);});tb.appendChild(row);});t.appendChild(tb);w.appendChild(h('div','tbl',[t]));return w;}
function stats(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','stats');arr(b.items).forEach(function(s){if(!s)return;var c=h('div','st');c.appendChild(txt('div','sl',s.label));c.appendChild(txt('div','sv',s.value));if(s.delta){var tone=s.tone||(/^\s*[-−]/.test(s.delta)?'down':'up');c.appendChild(txt('div','sd '+tone,s.delta));}g.appendChild(c);});w.appendChild(g);return w;}
var COLORS=['#4f8ef7','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4'];
function chart(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var labels=arr(b.labels),series=arr(b.series).filter(function(s){return s&&Array.isArray(s.data);});if(!labels.length||!series.length)return w;
 var W=640,H=240,P={l:44,r:12,t:12,b:30};var all=[];series.forEach(function(s){s.data.forEach(function(v){if(isFinite(+v))all.push(+v);});});var mx=Math.max.apply(null,all.concat([0])),mn=Math.min.apply(null,all.concat([0]));
 var step=Math.pow(10,Math.floor(Math.log10((mx-mn)||1)));var top=Math.ceil(mx/step)*step||1,bot=Math.floor(mn/step)*step;var iw=W-P.l-P.r,ih=H-P.t-P.b;function y(v){return P.t+ih-(v-bot)/(top-bot)*ih;}
 var ns='http://www.w3.org/2000/svg';function s(tag,a){var e=document.createElementNS(ns,tag);for(var k in a)e.setAttribute(k,a[k]);return e;}
 var svg=s('svg',{viewBox:'0 0 '+W+' '+H});var muted=getComputedStyle(document.documentElement).getPropertyValue('--muted');var lineC=getComputedStyle(document.documentElement).getPropertyValue('--line');
 for(var k=0;k<=4;k++){var v=bot+(top-bot)*k/4;var yy=y(v);svg.appendChild(s('line',{x1:P.l,x2:W-P.r,y1:yy,y2:yy,stroke:lineC,'stroke-width':1}));var tt=s('text',{x:P.l-8,y:yy+4,'text-anchor':'end','font-size':11,fill:muted});tt.textContent=(Math.abs(v)>=1000?(v/1000).toFixed(v%1000?1:0)+'k':+v.toFixed(2))+(b.unit&&k===4?b.unit:'');svg.appendChild(tt);}
 var bw=iw/labels.length;labels.forEach(function(l,i){var t=s('text',{x:P.l+bw*i+bw/2,y:H-10,'text-anchor':'middle','font-size':11,fill:muted});t.textContent=String(l).slice(0,14);svg.appendChild(t);});
 if(b.kind==='line'){series.forEach(function(se,si){var c=se.color||COLORS[si%6];var pts=se.data.map(function(v,i){return [P.l+bw*i+bw/2,y(+v)];});svg.appendChild(s('polyline',{points:pts.map(function(p){return p.join(',');}).join(' '),fill:'none',stroke:c,'stroke-width':2.4,'stroke-linejoin':'round','stroke-linecap':'round'}));pts.forEach(function(p,i){var d=s('circle',{cx:p[0],cy:p[1],r:3.4,fill:c});var ti=s('title',{});ti.textContent=se.name+' · '+labels[i]+': '+se.data[i]+(b.unit||'');d.appendChild(ti);svg.appendChild(d);});});}
 else{var gw=bw*.72/series.length;series.forEach(function(se,si){var c=se.color||COLORS[si%6];se.data.forEach(function(v,i){v=+v;var x=P.l+bw*i+bw*.14+gw*si;var y0=y(Math.max(0,bot)),y1=y(v);var r=s('rect',{x:x,y:Math.min(y0,y1),width:Math.max(2,gw-3),height:Math.max(1,Math.abs(y0-y1)),rx:4,fill:c});var ti=s('title',{});ti.textContent=se.name+' · '+labels[i]+': '+v+(b.unit||'');r.appendChild(ti);svg.appendChild(r);});});}
 var box=h('div','chart');if(series.length>1){var lg=h('div','legend');series.forEach(function(se,si){var sp=h('span');var ii=h('i');ii.style.background=se.color||COLORS[si%6];sp.appendChild(ii);sp.appendChild(document.createTextNode(se.name||''));lg.appendChild(sp);});box.appendChild(lg);}
 box.appendChild(svg);w.appendChild(box);return w;}
function callout(b){var ic={info:'ℹ️',tip:'💡',warning:'⚠️',danger:'⛔'}[b.tone]||'ℹ️';var c=h('div','co '+(b.tone||'info'));c.appendChild(txt('div','ci',ic));var body=h('div','');if(b.title)body.appendChild(txt('div','ct',b.title));body.appendChild(md(b.md||b.text||''));c.appendChild(body);return h('div','blk',[c]);}
function compare(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','cmp');arr(b.items).forEach(function(it){if(!it)return;var c=h('div','cmpc');c.appendChild(txt('div','h',it.title||''));var ul=h('ul');arr(it.points).forEach(function(p){var neg=/^\s*[-–−]\s*/.test(p);ul.appendChild(txt('li',neg?'neg':'',String(p).replace(/^\s*[-–−+]\s*/,'')));});arr(it.cons).forEach(function(p){ul.appendChild(txt('li','neg',p));});c.appendChild(ul);if(it.verdict)c.appendChild(txt('div','v',it.verdict));g.appendChild(c);});w.appendChild(g);return w;}
function steps(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var d=h('div','steps');arr(b.items).forEach(function(it,i){if(!it)return;var r=h('div','step');r.appendChild(txt('div','n',String(i+1)));var x=h('div','');x.appendChild(txt('div','tt',it.title||it));if(it.detail)x.appendChild(txt('div','td',it.detail));r.appendChild(x);d.appendChild(r);});w.appendChild(d);return w;}
function hero(b){var w=h('div','blk');var c=h('div','hero');c.appendChild(photo(b,'',{noText:true}));var ov=h('div','ov');if(b.eyebrow)ov.appendChild(txt('div','eb',b.eyebrow));if(b.title)ov.appendChild(txt('div','ht',b.title));if(b.md)ov.appendChild(md(b.md));c.appendChild(ov);w.appendChild(c);return w;}
function quote(b){var q=h('div','quote');q.appendChild(md(b.md||b.text||''));if(b.by)q.appendChild(txt('div','by','— '+b.by));return h('div','blk',[q]);}
function text(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));w.appendChild(md(b.md||b.text||''));return w;}
var R={text:text,images:images,map:mapBlock,places:places,cards:places,timeline:timeline,table:table,stats:stats,chart:chart,callout:callout,compare:compare,steps:steps,hero:hero,quote:quote};
/* ---------- render ---------- */
var S=I.S,app=I.app;
if(S.title)app.appendChild(txt('h1','t blk',S.title));if(S.subtitle)app.appendChild(txt('div','sub blk',S.subtitle));
var blocks=arr(S.blocks);var deferred=[];
/* maps first so timelines can link to them */
blocks.forEach(function(b,i){if(b&&b.type==='map')deferred[i]=mapBlock(b);});
blocks.forEach(function(b,i){if(!b)return;var f=R[b.type]||text;var node;try{node=b.type==='map'?deferred[i]:f(b);}catch(e){node=txt('div','blk','['+b.type+' could not render]');}
 if(node){node.style.animationDelay=Math.min(i*60,420)+'ms';app.appendChild(node);}});
if(I.SRC.length){var sw=h('div','blk');sw.appendChild(txt('div','lbl','Sources'));var sr=h('div','srcs');I.SRC.forEach(function(s,i){var c=h('button','src');c.setAttribute('data-url',s.url);var d=h('div','d');var im=document.createElement('img');im.src=I.fav(s.url);im.alt='';im.onerror=function(){im.remove();};d.appendChild(im);d.appendChild(document.createTextNode((i+1)+'. '+I.domain(s.url)));c.appendChild(d);c.appendChild(txt('div','s',s.title||s.url));sr.appendChild(c);});sw.appendChild(sr);app.appendChild(sw);}
var fu=arr(S.followups).filter(Boolean).slice(0,4);if(fu.length){var fw=h('div','blk');fw.appendChild(txt('div','lbl','Related'));var l=h('div','fu');fu.forEach(function(q){var bt=h('button','');bt.appendChild(icon('arrow'));bt.appendChild(document.createTextNode(String(q)));bt.onclick=function(){I.sendPrompt(String(q));};l.appendChild(bt);});fw.appendChild(l);app.appendChild(fw);}
document.querySelectorAll('.cite img').forEach(function(im){im.onerror=function(){im.remove();};});
setTimeout(I.reportHeight,50);
})();
</script>
</body>
</html>'''
