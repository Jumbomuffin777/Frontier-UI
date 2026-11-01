"""
title: Frontier UI
author: Zability (Claude Opus 5.5); inspired by ChatGPT Intelligent UI and thesysdev/open-intelligent-ui (MIT)
version: 1.2.1
description: ChatGPT-style generative UI: photo galleries, street maps with multi-day routes (self-hosted planet tiles), filterable place cards, itineraries, budgets, calculators, live weather and quotes, link previews, Gmail drafts, calendar export, real Word/Excel/PowerPoint/PDF files, and reading + editing your uploaded files with all 15 ArtCraft apps.
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

UA = {"User-Agent": "frontier-ui/1.1 (+https://github.com/Jumbomuffin777/Frontier-UI)"}
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


async def _resolve(spec, searx, do_images=True, do_maps=True, opts=None):
    """Fill photos, coordinates, street routes, live data and link previews in place. Never raises; failures degrade gracefully."""
    opts = opts or {}
    blocks = spec.get("blocks") if isinstance(spec.get("blocks"), list) else []
    img_jobs = []  # (target dict, key, query)
    live_jobs = []

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
            elif t == "map":
                if isinstance(b.get("days"), list):  # {"days":[{"label":"Day 1","places":[...]}]} -> flat places tagged with day
                    flat = []
                    for i, d in enumerate(b["days"]):
                        if isinstance(d, dict):
                            lab = str(d.get("label") or d.get("day") or d.get("title") or f"Day {i + 1}")
                            for p in d.get("places") or d.get("items") or []:
                                if isinstance(p, dict):
                                    p.setdefault("day", lab)
                                    flat.append(p)
                    b["places"] = flat + [p for p in (b.get("places") or []) if isinstance(p, dict)]
                    b.pop("days", None)
                if do_maps:
                    geo_tasks.append(b)
            elif t == "weather" and opts.get("live"):
                live_jobs.append(("weather", b))
            elif t == "stock" and opts.get("live"):
                live_jobs.append(("stock", b))
            elif t == "links":
                b["items"] = [({"url": it} if isinstance(it, str) else it) for it in items if isinstance(it, (dict, str))][:6]
                live_jobs.append(("links", b))

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
            mode = str(b.get("mode") or "auto").lower()
            mode = mode if mode in ("walk", "drive") else "auto"
            days = []
            for p in places:
                if p.get("day") and p["day"] not in days:
                    days.append(p["day"])

            async def route_for(ps):
                pts = [(p["lat"], p["lng"]) for p in ps if p.get("lat") is not None]
                if b.get("route", True if days else False) and 2 <= len(pts) <= 25 and max(_km(pts[0], q) for q in pts) < 400:
                    try:
                        return await _route(session, pts, mode)
                    except Exception:
                        return None
                return None

            if len(days) > 1:  # one street route per day; the "All" view shows every day's route in its own colour
                res = await asyncio.gather(*(route_for([p for p in places if p.get("day") == d]) for d in days), return_exceptions=True)
                b["day_routes"] = {d: (r if isinstance(r, dict) else None) for d, r in zip(days, res)}
                b["days_order"] = days
            else:
                b["route_geo"] = await route_for(places)

        async def run_live(kind, b):
            try:
                if kind == "weather":
                    b["weather"] = await asyncio.wait_for(_weather(session, b, opts.get("unit", "fahrenheit")), 7)
                elif kind == "stock":
                    syms = b.get("symbols") or ([b["symbol"]] if b.get("symbol") else [])
                    qs = await asyncio.gather(*(asyncio.wait_for(_quote(session, s), 7) for s in syms[:6]), return_exceptions=True)
                    b["quotes"] = [q if isinstance(q, dict) else {"symbol": str(s).upper(), "error": str(q)[:120]} for s, q in zip(syms, qs)]
                elif kind == "links":
                    await asyncio.gather(*(asyncio.wait_for(_preview(session, it, opts.get("bridge")), 9) for it in b["items"]), return_exceptions=True)
            except Exception as e:
                b["error"] = str(e)[:160]

        await asyncio.gather(*(run_img(*j) for j in img_jobs), *(run_map(b) for b in geo_tasks),
                             *(run_live(k, b) for k, b in live_jobs), return_exceptions=True)
        if opts.get("embed"):
            try:
                await asyncio.wait_for(_semantic_pass(session, spec, opts["embed"]), 4)
            except Exception:
                pass
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


def _origin(url):
    try:
        u = urlparse(url)
        return f"{u.scheme}://{u.netloc}" if u.scheme in ("http", "https") and u.netloc else ""
    except Exception:
        return ""


def _build_html(spec, theme, cdn, tiles=""):
    nonce = secrets.token_urlsafe(16)
    cdn = cdn.rstrip("/")
    hosts = " ".join(sorted({h for h in (_origin(cdn), _origin(tiles)) if h}))
    html = _HTML.replace("__NONCE__", nonce).replace("__THEME__", "dark" if theme == "dark" else "light")
    html = html.replace("__CDN__", cdn).replace("__CDNHOST__", hosts).replace("__TILESHOST__", _origin(tiles) or "https:")
    return html.replace("__SPEC__", _safe_json(spec))




# ======================= v1.1: live data, page previews, embeddings, Craft apps, files & notes =======================
import base64
import html as _html
import io
import ipaddress
import os
import socket
import time
import uuid
from urllib.parse import quote, urljoin

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
              "Accept-Language": "en-US,en;q=0.8"}
_LIVE: dict = {}
_CARDS: dict = {}  # card id -> spec, so "export this card" / "save to notes" work without the model re-sending content
CRAFT_APPS = {
    "wordcraft": ("WordCraft", "Documents (Word)", "📝"), "gridcraft": ("GridCraft", "Spreadsheets (Excel)", "📊"),
    "deckcraft": ("DeckCraft", "Presentations (PowerPoint)", "📽️"), "pdfcraft": ("PdfCraft", "PDF editor", "📄"),
    "photocraft": ("PhotoCraft", "Photo editing", "🖼️"), "lightcraft": ("LightCraft", "Photo development (RAW)", "🌅"),
    "vectorcraft": ("VectorCraft", "Vector illustration", "✒️"), "designcraft": ("DesignCraft", "Page layout", "📰"),
    "figcraft": ("FigCraft", "UI design & prototyping", "🧩"), "filmcraft": ("FilmCraft", "Video editing", "🎬"),
    "effectcraft": ("EffectCraft", "Motion graphics & VFX", "✨"), "soundcraft": ("SoundCraft", "Audio recording & mixing", "🎚️"),
    "cadcraft": ("CADCraft", "CAD drafting", "📐"), "solidcraft": ("SolidCraft", "Parametric 3D CAD", "🧊"),
    "craft-anything": ("Craft Anything", "See how any software works", "🔍"),
}
CRAFT_EXT = {  # file extension -> app that reads / edits it (mirrors the bridge)
    **{e: "wordcraft" for e in "docx doc odt rtf md dotx docm tex txt".split()},
    **{e: "gridcraft" for e in "xlsx xlsm xlsb csv tsv ods".split()},
    **{e: "deckcraft" for e in "pptx potx ppsx deckcraft".split()},
    **{e: "cadcraft" for e in "dxf dwg dwt".split()}, **{e: "solidcraft" for e in "step stp stl 3mf iges igs sc".split()},
    **{e: "soundcraft" for e in "wav flac mp3 mid aif aiff ogg m4a aac scraft".split()}, "pdf": "pdfcraft",
    **{e: "vectorcraft" for e in "svg ai eps emf".split()},
    **{e: "photocraft" for e in "png jpg jpeg webp psd gif bmp tif tiff avif kra pcraft exr".split()},
    **{e: "filmcraft" for e in "mp4 mov webm mkv avi mxf".split()}, "idml": "designcraft",
    **{e: "figcraft" for e in "fig figcraft sketch penpot".split()},
    **{e: "lightcraft" for e in "dng heic cr2 cr3 nef arw raf orf rw2 pef".split()}, "ecproj": "effectcraft",
}
FORMAT_KIND = {"docx": "doc", "pdf": "doc", "odt": "doc", "rtf": "doc", "html": "doc", "md": "doc", "txt": "doc",
               "xlsx": "sheet", "csv": "sheet", "pptx": "deck", "gif": "deck"}
FORMAT_APP = {"doc": "wordcraft", "sheet": "gridcraft", "deck": "deckcraft"}


def _live_get(key, ttl):
    v = _LIVE.get(key)
    return v[1] if v and time.time() - v[0] < ttl else None


def _live_put(key, val):
    _LIVE[key] = (time.time(), val)
    if len(_LIVE) > 400:
        for k in sorted(_LIVE, key=lambda k: _LIVE[k][0])[:100]:
            _LIVE.pop(k, None)
    return val


def _public_host(url):
    """SSRF guard: only http(s) URLs that resolve to global addresses."""
    try:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))
        return all(ipaddress.ip_address(i[4][0]).is_global for i in infos)
    except Exception:
        return False


async def _fetch_text(session, url, timeout=5, limit=1_500_000, headers=None):
    async with session.get(url, headers=headers or BROWSER_UA, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True) as r:
        if r.status >= 400:
            raise RuntimeError(f"HTTP {r.status}")
        if not _public_host(str(r.url)):
            raise RuntimeError("redirected to a private address")
        raw = await r.content.read(limit)
        return raw.decode(r.charset or "utf-8", "replace"), str(r.url)


# ---------- weather (Open-Meteo, keyless) ----------
WMO = {0: ("Clear", "☀️"), 1: ("Mostly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"), 45: ("Fog", "🌫️"),
       48: ("Rime fog", "🌫️"), 51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"), 55: ("Heavy drizzle", "🌧️"),
       56: ("Freezing drizzle", "🌧️"), 57: ("Freezing drizzle", "🌧️"), 61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"),
       65: ("Heavy rain", "🌧️"), 66: ("Freezing rain", "🌧️"), 67: ("Freezing rain", "🌧️"), 71: ("Light snow", "🌨️"),
       73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"), 77: ("Snow grains", "🌨️"), 80: ("Showers", "🌦️"), 81: ("Showers", "🌧️"),
       82: ("Violent showers", "⛈️"), 85: ("Snow showers", "🌨️"), 86: ("Snow showers", "❄️"), 95: ("Thunderstorm", "⛈️"),
       96: ("Thunderstorm, hail", "⛈️"), 99: ("Thunderstorm, hail", "⛈️")}


async def _weather(session, b, unit):
    loc = str(b.get("location") or b.get("area") or "").strip()
    days = max(1, min(10, int(b.get("days") or 5)))
    key = ("wx", loc.lower(), b.get("lat"), b.get("lng"), days, unit)
    hit = _live_get(key, 900)
    if hit:
        return hit
    lat, lng, label = b.get("lat"), b.get("lng"), loc
    if lat is None or lng is None:
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        g = await _get_json(session, "https://geocoding-api.open-meteo.com/v1/search",
                            {"name": parts[0] if parts else loc, "count": 8, "language": "en"}, 4)
        res = (g or {}).get("results") or []
        if not res:
            raise RuntimeError("place not found")
        want = " ".join(parts[1:]).lower()
        best = next((r for r in res if want and any(want in str(r.get(k, "")).lower() or str(r.get(k, "")).lower() in want
                                                    for k in ("country", "admin1", "country_code") if r.get(k))), res[0])
        lat, lng = best["latitude"], best["longitude"]
        label = ", ".join(x for x in [best.get("name"), best.get("admin1") if best.get("country_code") == "US" else best.get("country")] if x)
    imperial = unit == "fahrenheit"
    f = await _get_json(session, "https://api.open-meteo.com/v1/forecast", {
        "latitude": lat, "longitude": lng, "timezone": "auto", "forecast_days": days,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
        "hourly": "temperature_2m,precipitation_probability", "forecast_hours": 24,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
        "temperature_unit": unit, "wind_speed_unit": "mph" if imperial else "kmh"}, 5)
    cur, d, hr = f.get("current") or {}, f.get("daily") or {}, f.get("hourly") or {}
    code = int(cur.get("weather_code") or 0)
    out = {"label": label, "lat": lat, "lng": lng, "unit": "°F" if imperial else "°C", "wind_unit": "mph" if imperial else "km/h",
           "now": {"t": cur.get("temperature_2m"), "feels": cur.get("apparent_temperature"), "rh": cur.get("relative_humidity_2m"),
                   "wind": cur.get("wind_speed_10m"), "text": WMO.get(code, ("", "🌡️"))[0], "icon": WMO.get(code, ("", "🌡️"))[1],
                   "day": cur.get("is_day", 1)},
           "hourly": [{"time": t[-5:], "t": v, "p": p} for t, v, p in zip(hr.get("time", []), hr.get("temperature_2m", []),
                                                                        hr.get("precipitation_probability", []) or [None] * 24)],
           "daily": [{"date": dt, "hi": hi, "lo": lo, "p": p, "icon": WMO.get(int(c or 0), ("", "🌡️"))[1], "text": WMO.get(int(c or 0), ("", ""))[0],
                      "sunrise": (sr or "")[-5:], "sunset": (ss or "")[-5:]}
                     for dt, c, hi, lo, p, sr, ss in zip(d.get("time", []), d.get("weather_code", []), d.get("temperature_2m_max", []),
                                                         d.get("temperature_2m_min", []), d.get("precipitation_probability_max", []),
                                                         d.get("sunrise", []), d.get("sunset", []))],
           "fetched": int(time.time()), "source": "Open-Meteo"}
    return _live_put(key, out)


# ---------- quotes (Yahoo Finance chart API, keyless) ----------
async def _yahoo(session, sym, rng, itv):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym)}"
    async with session.get(url, params={"range": rng, "interval": itv, "includePrePost": "false"}, headers=UA,
                           timeout=aiohttp.ClientTimeout(total=5)) as r:
        j = await r.json(content_type=None)
    res = ((j or {}).get("chart") or {}).get("result") or []
    if not res:
        raise RuntimeError(((j or {}).get("chart") or {}).get("error", {}).get("description") or "no data")
    r0 = res[0]
    q = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    pts = [[t, round(c, 4)] for t, c in zip(r0.get("timestamp") or [], q.get("close") or []) if c is not None]
    return r0.get("meta") or {}, pts


async def _quote(session, sym):
    sym = re.sub(r"[^A-Za-z0-9.^=\-]", "", str(sym)).upper()[:20]
    key = ("q", sym)
    hit = _live_get(key, 120)
    if hit:
        return hit
    ranges = await asyncio.gather(_yahoo(session, sym, "1d", "5m"), _yahoo(session, sym, "1mo", "1d"),
                                  _yahoo(session, sym, "1y", "1wk"), return_exceptions=True)
    ok = [r for r in ranges if not isinstance(r, Exception)]
    if not ok:
        raise RuntimeError(str(ranges[0]))
    meta = ok[0][0]
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") if not isinstance(ranges[0], Exception) else None
    prev = meta.get("previousClose") or prev
    out = {"symbol": sym, "name": meta.get("longName") or meta.get("shortName") or sym, "price": price, "prev": prev,
           "currency": meta.get("currency") or "", "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "",
           "time": meta.get("regularMarketTime"), "high52": meta.get("fiftyTwoWeekHigh"), "low52": meta.get("fiftyTwoWeekLow"),
           "series": {k: (r[1] if not isinstance(r, Exception) else []) for k, r in zip(("1D", "1M", "1Y"), ranges)},
           "fetched": int(time.time()), "source": "Yahoo Finance"}
    return _live_put(key, out)


# ---------- page previews (og tags + reader excerpt + optional Chromium screenshot via the Craft bridge) ----------
def _meta(html_text, *names):
    for n in names:
        m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*>' % re.escape(n), html_text, re.I)
        if m:
            c = re.search(r'content=["\']([^"\']*)["\']', m.group(0), re.I)
            if c and c.group(1).strip():
                return _html.unescape(c.group(1).strip())
    return ""


def _reader(html_text, limit=900):
    body = re.sub(r"(?is)<(script|style|noscript|nav|header|footer|aside|form|svg|figure)[^>]*>.*?</\1>", " ", html_text)
    paras = []
    for m in re.finditer(r"(?is)<p[^>]*>(.*?)</p>", body):
        t = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()
        if len(t) > 60 and not re.search(r"cookie|subscribe|sign up|javascript", t, re.I):
            paras.append(t)
        if sum(len(p) for p in paras) > limit:
            break
    return paras[:5]


async def _preview(session, it, bridge):
    url = str(it.get("url") or "")
    if not _public_host(url):
        return
    key = ("pv", url, bool(bridge))
    hit = _live_get(key, 3600)
    if hit:
        it.update({k: v for k, v in hit.items() if not it.get(k)})
        return
    out = {}

    async def page():
        wm = re.match(r"https?://([a-z\-]+)\.(?:m\.)?wikipedia\.org/wiki/([^?#]+)", url)
        if wm:  # Wikipedia: the REST summary is cleaner than scraping
            j = await _get_json(session, f"https://{wm.group(1)}.wikipedia.org/api/rest_v1/page/summary/{wm.group(2)}", None, 5)
            if j and j.get("extract"):
                out.update({"title": j.get("title", ""), "description": j.get("description", ""), "site": "Wikipedia",
                            "reader": [p for p in j["extract"].split("\n") if p.strip()][:4]})
                img = (j.get("thumbnail") or j.get("originalimage") or {}).get("source")
                if img:
                    out["og_image"] = img
                return
        try:  # honest UA first (Wikimedia & co. require it), browser UA for sites that block bots
            text, final = await _fetch_text(session, url, 5, headers=UA)
            if not re.search(r"<p[\s>]", text):
                raise RuntimeError("no body")
        except Exception:
            text, final = await _fetch_text(session, url, 5)
        out["title"] = _meta(text, "og:title", "twitter:title") or _html.unescape((re.search(r"(?is)<title[^>]*>(.*?)</title>", text) or [None, ""])[1]).strip()
        out["description"] = _meta(text, "og:description", "description", "twitter:description")
        out["site"] = _meta(text, "og:site_name") or urlparse(final).hostname.replace("www.", "")
        img = _meta(text, "og:image", "twitter:image", "og:image:url")
        if img:
            img = urljoin(final, img)
            if img.startswith("https://"):
                out["og_image"] = img
        out["published"] = _meta(text, "article:published_time", "og:updated_time")[:10]
        out["reader"] = _reader(text)

    async def shot():
        r = await _bridge_call(session, bridge, "/screenshot", {"url": url}, 18)
        if r.get("b64"):
            out["shot"] = "data:image/jpeg;base64," + r["b64"]

    jobs = [page()] + ([shot()] if bridge and bridge.get("shots") else [])
    await asyncio.gather(*jobs, return_exceptions=True)
    _live_put(key, out)
    it.update({k: v for k, v in out.items() if not it.get(k)})


# ---------- EmbeddingGemma: rerank photo candidates, snap timeline items onto map places ----------
async def _embed(session, cfg, texts):
    if not texts:
        return None
    if cfg.get("fn"):  # Open WebUI's own configured embedding engine (e.g. EmbeddingGemma) - no extra keys needed
        vecs = await cfg["fn"](texts, prefix=None, user=None)
        return vecs if isinstance(vecs, list) and len(vecs) == len(texts) else None
    if not cfg.get("url"):
        return None
    hdr = {"Authorization": f"Bearer {cfg['key']}"} if cfg.get("key") else {}
    async with session.post(cfg["url"].rstrip("/") + "/v1/embeddings", json={"model": cfg.get("model") or "embeddinggemma-2", "input": texts},
                            headers=hdr, timeout=aiohttp.ClientTimeout(total=cfg.get("timeout", 4))) as r:
        j = await r.json(content_type=None)
    data = sorted(j.get("data") or [], key=lambda d: d.get("index", 0))
    vecs = [d.get("embedding") for d in data]
    return vecs if len(vecs) == len(texts) else None


def _cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1.0
    return num / den


async def _semantic_pass(session, spec, cfg):
    """One batched embedding call: reorder image candidates by caption relevance and link timeline rows to map pins."""
    texts, jobs = [], []

    def add(t):
        texts.append(str(t)[:300])
        return len(texts) - 1

    for b in spec.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        for it in (b.get("items") if isinstance(b.get("items"), list) else []) + ([b] if b.get("type") == "hero" else []):
            if isinstance(it, dict) and len(it.get("candidates") or []) > 1:
                q = it.get("query") or it.get("caption") or it.get("name") or it.get("title") or it.get("image")
                cands = it["candidates"][:6]
                if q and all(c.get("title") for c in cands):
                    jobs.append(("img", it, add(f"task: search result | query: {q}"), [add(f"title: none | text: {c['title']}") for c in cands]))
    places = []
    for b in spec.get("blocks") or []:
        if isinstance(b, dict) and b.get("type") == "map":
            places += [p.get("name") for p in b.get("places") or [] if isinstance(p, dict) and p.get("name")]
    if places:
        pidx = [add(f"title: none | text: {p}") for p in places]
        lower = [p.lower() for p in places]
        for b in spec.get("blocks") or []:
            if isinstance(b, dict) and b.get("type") == "timeline":
                for it in b.get("items") or []:
                    if not isinstance(it, dict):
                        continue
                    ref = str(it.get("place") or "").lower()
                    if ref and any(ref == n or ref in n or n in ref for n in lower):
                        continue
                    q = " ".join(str(x) for x in (it.get("place"), it.get("title"), it.get("detail")) if x)
                    if q:
                        jobs.append(("tl", it, add(f"task: search result | query: {q}"), pidx))
    if not jobs or len(texts) > 256:
        return
    vecs = await _embed(session, cfg, texts)
    if not vecs:
        return
    for kind, it, qi, cis in jobs:
        scores = [_cos(vecs[qi], vecs[c]) for c in cis]
        if kind == "img":
            order = sorted(range(len(cis)), key=lambda k: -scores[k])
            if scores[order[0]] - scores[0] > 0.04:  # only reorder on a clear win
                head = [it["candidates"][k] for k in order]
                it["candidates"] = head + it["candidates"][len(cis):]
        else:
            order = sorted(range(len(cis)), key=lambda k: -scores[k])
            best, second = scores[order[0]], (scores[order[1]] if len(order) > 1 else 0)
            if best > 0.55 or (best > 0.35 and best - second > 0.08):  # confident, or a clear winner
                it["place"] = places[order[0]]


# ---------- Craft bridge (runs inside the Craft apps container) ----------
async def _bridge_call(session, cfg, path, payload, timeout=60):
    if not cfg or not cfg.get("url") or not cfg.get("token"):
        raise RuntimeError("Craft bridge is not configured (valves craft_bridge_url / craft_bridge_token)")
    async with session.post(cfg["url"].rstrip("/") + path, json=payload, headers={"X-Craft-Token": cfg["token"]},
                            timeout=aiohttp.ClientTimeout(total=timeout)) as r:
        j = await r.json(content_type=None)
        if r.status >= 400:
            raise RuntimeError(j.get("error") or f"bridge HTTP {r.status}")
        return j


# ---------- the user's uploaded files (for reading / editing with the Craft apps) ----------
_MADE: dict = {}  # name/id -> Open WebUI file id of files this tool produced, so edits can be chained


def _file_refs(__files__, __messages__, uid=""):
    """Every file the conversation knows about, newest first: [{id, name}]"""
    out, seen = [], set()

    def add(f):
        if not isinstance(f, dict):
            return
        inner = f.get("file") if isinstance(f.get("file"), dict) else {}
        fid = f.get("id") or inner.get("id")
        name = f.get("name") or inner.get("filename") or (inner.get("meta") or {}).get("name") or ""
        if fid and fid not in seen and f.get("type", "file") in ("file", "doc", "image", None, ""):
            seen.add(fid)
            out.append({"id": fid, "name": name})

    for f in reversed(__files__ or []):
        add(f)
    for m in reversed(__messages__ or []):
        for f in reversed((m or {}).get("files") or []):
            add(f)
    for k, fid in reversed(list(_MADE.items())):
        owner, _, name = k.partition("|")
        if owner == uid and fid not in seen:
            seen.add(fid)
            out.append({"id": fid, "name": name})
    return out


async def _load_file(ref, __files__, __messages__, user):
    """Find one of the user's files by id, (partial) name or 'latest'; return (name, bytes, id)."""
    from open_webui.models.files import Files
    from open_webui.storage.provider import Storage
    uid = (user or {}).get("id", "")
    refs = _file_refs(__files__, __messages__, uid)
    ref = str(ref or "").strip()
    pick = None
    if ref:
        low = ref.lower().split("/")[-1]
        pick = next((r for r in refs if r["id"] == ref or low in r["id"]), None) \
            or next((r for r in refs if r["name"].lower() == low), None) \
            or next((r for r in refs if r["name"].lower().rsplit(".", 1)[0] == low.rsplit(".", 1)[0]), None) \
            or next((r for r in refs if low in r["name"].lower()), None)
    elif refs:
        pick = refs[0]
    if not pick:
        names = ", ".join(r["name"] for r in refs[:10]) or "none"
        raise FileNotFoundError(f"No file matching '{ref}'. Files in this chat: {names}. Ask the user to attach the file.")
    fm = Files.get_file_by_id(pick["id"])
    fm = await fm if asyncio.iscoroutine(fm) else fm
    if not fm:
        raise FileNotFoundError(f"File {pick['name']} is no longer available")
    if fm.user_id != uid and (user or {}).get("role") != "admin":
        raise PermissionError("That file belongs to another user.")
    local = await asyncio.to_thread(Storage.get_file, fm.path)
    data = await asyncio.to_thread(lambda: open(local, "rb").read())
    return (fm.filename or pick["name"]), data, fm.id


# ---------- Open WebUI files & notes ----------
async def _store_file(user, name, data, mime):
    from open_webui.models.files import FileForm, Files
    from open_webui.storage.provider import Storage
    fid = str(uuid.uuid4())
    tags = {"OpenWebUI-User-Email": user.get("email", ""), "OpenWebUI-User-Id": user.get("id", ""),
            "OpenWebUI-User-Name": user.get("name", ""), "OpenWebUI-File-Id": fid}
    _contents, path = await asyncio.to_thread(Storage.upload_file, io.BytesIO(data), f"{fid}_{name}", tags)
    res = Files.insert_new_file(user["id"], FileForm(id=fid, filename=name, path=path, data={},
                                                     meta={"name": name, "content_type": mime, "size": len(data), "source": "frontier_ui"}))
    if asyncio.iscoroutine(res):
        await res
    _MADE[f"{user.get('id', '')}|{name.lower()}"] = fid
    while len(_MADE) > 500:
        _MADE.pop(next(iter(_MADE)))
    return fid, f"/api/v1/files/{fid}/content"


async def _create_note(user, title, md_text):
    from open_webui.models.notes import NoteForm, Notes
    html_body = _md_to_html(md_text)
    res = Notes.insert_new_note(user["id"], NoteForm(title=title[:200], data={"content": {"json": None, "html": html_body, "md": md_text}},
                                                     meta=None, access_grants=[]))
    note = await res if asyncio.iscoroutine(res) else res
    return getattr(note, "id", None)


def _md_to_html(md_text):
    out, in_list = [], False
    for line in str(md_text).splitlines():
        esc = _html.escape(line)
        esc = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', esc)
        m = re.match(r"^\s*[-*]\s+(.*)", esc)
        if m:
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{m.group(1)}</li>"); continue
        if in_list:
            out.append("</ul>"); in_list = False
        h = re.match(r"^(#{1,3})\s+(.*)", esc)
        if h:
            out.append(f"<h{len(h.group(1))}>{h.group(2)}</h{len(h.group(1))}>")
        elif esc.strip():
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return "".join(out)


# ---------- spec -> markdown / sheet rows / slides (exports, notes, email) ----------
def _first_photo(it):
    for c in (it or {}).get("candidates") or []:
        if isinstance(c, dict) and str(c.get("src", "")).startswith("https://"):
            return c["src"]
    img = (it or {}).get("image") or (it or {}).get("src")
    return img if isinstance(img, str) and img.startswith("https://") else None


def _spec_md(spec):
    L = [f"# {spec.get('title') or 'Frontier UI'}"]
    if spec.get("subtitle"):
        L.append(f"*{spec['subtitle']}*")
    for b in spec.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        t, items = b.get("type"), [x for x in (b.get("items") or []) if x]
        if b.get("title"):
            L.append(f"\n## {b['title']}")
        if t in ("text", "quote", "callout"):
            if t == "callout" and b.get("title") and not items:
                pass
            L.append(str(b.get("md") or b.get("text") or "") + (f"\n— {b['by']}" if b.get("by") else ""))
        elif t == "hero":
            L.append(f"**{b.get('title', '')}** {b.get('md', '')}")
        elif t in ("places", "cards"):
            for it in items:
                bits = [f"★ {it['rating']}" if it.get("rating") else "", it.get("price") or "", it.get("subtitle") or ""]
                L.append(f"- **{it.get('name') or it.get('title', '')}** ({' · '.join(x for x in bits if x)}) — {it.get('description', '')}"
                         + (f" [link]({it['url']})" if it.get("url") else ""))
        elif t == "map":
            days = {}
            for p in b.get("places") or []:
                days.setdefault(p.get("day") or "", []).append(p)
            for d, ps in days.items():
                if d:
                    L.append(f"\n**{d}**")
                for i, p in enumerate(ps, 1):
                    L.append(f"{i}. {p.get('icon', '')} {p.get('name', '')}" + (f" — {p['time']}" if p.get("time") else "") + (f": {p['note']}" if p.get("note") else ""))
        elif t == "timeline":
            for it in items:
                L.append(f"- **{it.get('time', '')}** {it.get('title', '')}" + (f" — {it['detail']}" if it.get("detail") else ""))
        elif t in ("steps",):
            for i, it in enumerate(items, 1):
                L.append(f"{i}. **{it.get('title', it) if isinstance(it, dict) else it}**" + (f" — {it.get('detail')}" if isinstance(it, dict) and it.get("detail") else ""))
        elif t == "table":
            cols = b.get("columns") or []
            if cols:
                L.append("| " + " | ".join(map(str, cols)) + " |")
                L.append("|" + "---|" * len(cols))
            for r in b.get("rows") or []:
                L.append("| " + " | ".join(str(c) for c in r) + " |")
        elif t == "stats":
            for s in items:
                L.append(f"- {s.get('label', '')}: **{s.get('value', '')}** {s.get('delta', '')}")
        elif t == "compare":
            for it in items:
                L.append(f"\n**{it.get('title', '')}**")
                L += [f"- {p}" for p in it.get("points") or []]
                if it.get("verdict"):
                    L.append(f"*{it['verdict']}*")
        elif t == "budget":
            cur = b.get("currency", "$")
            tot = 0
            for it in items:
                amt = float(it.get("amount") or 0) * float(it.get("qty") or 1)
                tot += amt
                L.append(f"- {it.get('label', '')}: {cur}{amt:,.0f}" + (f" ({it.get('qty')} × {cur}{float(it.get('amount') or 0):,.0f})" if it.get("qty") else ""))
            L.append(f"- **Total: {cur}{tot:,.0f}**")
        elif t == "weather" and b.get("weather"):
            w = b["weather"]
            L.append(f"{w['label']}: {w['now']['icon']} {w['now']['t']}{w['unit']} {w['now']['text']}")
            L += [f"- {d['date']}: {d['icon']} {d['hi']}/{d['lo']}{w['unit']}, rain {d['p']}%" for d in w.get("daily", [])]
        elif t == "stock":
            for q in b.get("quotes") or []:
                if q.get("price") is not None:
                    ch = (q["price"] - q["prev"]) / q["prev"] * 100 if q.get("prev") else 0
                    L.append(f"- **{q['symbol']}** {q['name']}: {q['price']:,.2f} {q['currency']} ({ch:+.2f}%)")
        elif t == "links":
            for it in items:
                L.append(f"- [{it.get('title') or it.get('url')}]({it.get('url')}) — {it.get('description', '')}")
        elif t == "chart":
            for s in b.get("series") or []:
                L.append(f"- {s.get('name', '')}: " + ", ".join(f"{l}={v}" for l, v in zip(b.get("labels") or [], s.get("data") or [])))
        elif t == "email":
            L.append(f"To: {b.get('to', '')}\nSubject: {b.get('subject', '')}\n\n{b.get('body', '')}")
    src = [s for s in spec.get("sources") or [] if isinstance(s, dict) and s.get("url")]
    if src:
        L.append("\n## Sources")
        L += [f"{i}. [{s.get('title') or s['url']}]({s['url']})" for i, s in enumerate(src, 1)]
    return "\n".join(L).strip() + "\n"


def _spec_rows(spec, which=None):
    """Best table in the card -> [header, *rows]."""
    cands = []
    for b in spec.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        t, items = b.get("type"), [x for x in (b.get("items") or []) if isinstance(x, dict)]
        if t == "table" and b.get("rows"):
            cands.append([b.get("columns") or []] + b["rows"])
        elif t in ("places", "cards") and items:
            cands.append([["Name", "Rating", "Price", "Type", "Description", "Tags", "Link"]] +
                         [[i.get("name") or i.get("title", ""), i.get("rating", ""), i.get("price", ""), i.get("subtitle", ""),
                           i.get("description", ""), ", ".join(i.get("tags") or []), i.get("url", "")] for i in items])
        elif t == "budget" and items:
            cands.append([["Item", "Unit cost", "Qty", "Total"]] + [[i.get("label", ""), i.get("amount", 0), i.get("qty", 1),
                                                                    float(i.get("amount") or 0) * float(i.get("qty") or 1)] for i in items])
        elif t == "timeline" and items:
            cands.append([["Time", "Activity", "Details", "Place"]] + [[i.get("time", ""), i.get("title", ""), i.get("detail", ""), i.get("place", "")] for i in items])
        elif t == "map" and b.get("places"):
            cands.append([["Day", "Stop", "Time", "Note", "Lat", "Lng"]] + [[p.get("day", ""), p.get("name", ""), p.get("time", ""), p.get("note", ""), p.get("lat"), p.get("lng")] for p in b["places"]])
        elif t == "chart" and b.get("labels"):
            ser = b.get("series") or []
            cands.append([[""] + [s.get("name", "") for s in ser]] + [[l] + [(s.get("data") or [None] * 99)[i] for s in ser] for i, l in enumerate(b["labels"])])
        elif t == "stock":
            for q in b.get("quotes") or []:
                cands.append([["Date", f"{q['symbol']} close"]] + [[time.strftime("%Y-%m-%d", time.gmtime(t0)), v] for t0, v in q.get("series", {}).get("1Y", [])])
    if not cands:
        return None
    if isinstance(which, int) and 0 <= which < len(cands):
        return cands[which]
    return max(cands, key=len)


def _spec_slides(spec):
    S = [{"title": spec.get("title") or "Overview", "body": spec.get("subtitle") or "", "layout": "title"}]
    for b in spec.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        t, items = b.get("type"), [x for x in (b.get("items") or []) if x]
        title = b.get("title") or ""
        if t == "text":
            body = re.sub(r"\[(\d+)\]", "", str(b.get("md") or ""))
            bullets = [re.sub(r"^\s*[-*]\s*", "", x).replace("**", "") for x in body.splitlines() if x.strip()]
            S.append({"title": title or "Summary", "body": bullets[:8]})
        elif t == "hero":
            S.append({"title": b.get("title") or title, "body": str(b.get("md") or ""), "image": _first_photo(b)})
        elif t == "images":
            for it in items[:3]:
                if isinstance(it, dict) and _first_photo(it):
                    S.append({"title": it.get("caption") or title or "", "body": "", "image": _first_photo(it)})
        elif t in ("places", "cards"):
            for it in [i for i in items if isinstance(i, dict)][:6]:
                meta = " · ".join(str(x) for x in [f"★ {it['rating']}" if it.get("rating") else "", it.get("price"), it.get("subtitle")] if x)
                S.append({"title": it.get("name") or it.get("title", ""), "body": [x for x in [meta, it.get("description", "")] + list(it.get("tags") or []) if x],
                          "image": _first_photo(it)})
        elif t == "map":
            days = {}
            for p in b.get("places") or []:
                days.setdefault(p.get("day") or title or "Route", []).append(p)
            for d, ps in days.items():
                S.append({"title": d, "body": [f"{p.get('icon', '')} {p.get('name', '')}" + (f" — {p['time']}" if p.get("time") else "") for p in ps][:10]})
        elif t == "timeline":
            S.append({"title": title or "Schedule", "body": [f"{i.get('time', '')}  {i.get('title', '')}" for i in items if isinstance(i, dict)][:10]})
        elif t in ("steps", "stats", "compare"):
            if t == "compare":
                for it in items[:3]:
                    S.append({"title": it.get("title", ""), "body": list(it.get("points") or [])[:7] + ([it["verdict"]] if it.get("verdict") else [])})
            else:
                S.append({"title": title or ("Steps" if t == "steps" else "Key numbers"),
                          "body": [(f"{i.get('label')}: {i.get('value')} {i.get('delta', '')}" if t == "stats" else f"{i.get('title', '')} — {i.get('detail', '')}") for i in items if isinstance(i, dict)][:8]})
        elif t == "chart" and b.get("labels") and b.get("series"):
            S.append({"title": title or "Chart", "chart": {"type": "line" if b.get("kind") == "line" else "column", "categories": b["labels"],
                                                         "series": [{"name": s.get("name", ""), "values": s.get("data", [])} for s in b["series"]]}})
        elif t == "budget" and items:
            S.append({"title": title or "Budget", "body": [f"{i.get('label')}: {b.get('currency', '$')}{float(i.get('amount') or 0) * float(i.get('qty') or 1):,.0f}" for i in items],
                      "chart": {"type": "pie", "categories": [i.get("label", "") for i in items],
                                "series": [{"name": "Cost", "values": [float(i.get("amount") or 0) * float(i.get("qty") or 1) for i in items]}]}})
        elif t == "table" and b.get("rows"):
            S.append({"title": title or "Table", "body": [" · ".join(str(c) for c in r) for r in b["rows"][:10]]})
        elif t == "callout":
            S.append({"title": b.get("title") or "Note", "body": str(b.get("md") or "")})
    return S[:40]


_HTML = r'''<!DOCTYPE html>
<html lang="en" data-theme="__THEME__" class="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-__NONCE__' __CDNHOST__; style-src 'unsafe-inline' __CDNHOST__; img-src https: http: data: blob:; connect-src https: __TILESHOST__; worker-src blob:; child-src blob:; font-src https: data:; base-uri 'none'; form-action 'none'">
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


_HTML += r'''SVG.ext='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>';
SVG.copy='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/></svg>';
SVG.mail='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>';
SVG.cal='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>';
SVG.doc='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/></svg>';
SVG.note='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13 7l4 4"/></svg>';
SVG.dl='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>';
SVG.chev='<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>';
window.IUI={S:S,app:app,SRC:SRC,h:h,txt:txt,arr:arr,md:md,photo:photo,scroller:scroller,label:label,icon:icon,SVG:SVG,isDark:isDark,openLink:openLink,sendPrompt:sendPrompt,reportHeight:reportHeight,fav:fav,domain:domain,esc:esc,
 CDN:'__CDN__',NONCE:'__NONCE__',UI:(S&&S._ui)||{},X:{}};
})();
</script>
'''
_HTML = _HTML.replace(' onerror="this.remove()"', '').replace(
    ".ti .thumb img{width:100%;height:100%;object-fit:cover}",
    ".ti .thumb img{width:100%;height:100%;object-fit:cover}.ti .thumb .ph{aspect-ratio:auto;height:100%;border-radius:0}").replace(
    "var p=new URL(String(u||''),location.href);", "var B=(window.IUI&&IUI.UI&&IUI.UI.base)||(origin!=='*'?origin:'');var s=String(u||'');if(s.charAt(0)==='/'&&s.charAt(1)!=='/'&&B)s=(B.slice(-1)==='/'?B.slice(0,-1):B)+s;var p=new URL(s,B?B+'/':location.href);")


_HTML += r'''<style>
/* ---- v1.1 blocks ---- */
.dtabs{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 8px}
.dtab{border:1px solid var(--line);background:var(--surface);color:var(--fg);border-radius:999px;padding:4px 11px;font:500 12.5px/1.4 inherit;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.dtab i{width:9px;height:9px;border-radius:50%;display:inline-block}
.dtab.on{background:var(--fg);color:var(--surface2);border-color:var(--fg)}
.ti.off{opacity:.32}
.mlink{display:block;margin-top:4px;font-size:12px;color:var(--accent);text-decoration:none}
.fbar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:0 0 10px}
.fsel{border:1px solid var(--line);background:var(--surface);color:var(--fg);border-radius:8px;padding:4px 8px;font:500 12.5px inherit}
.fchip{border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:3px 10px;font:500 12px/1.4 inherit;cursor:pointer}
.fchip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.fcount{font-size:12px;color:var(--faint);margin-left:4px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:14px 16px}
.row2{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.muted{color:var(--muted)}.faint{color:var(--faint);font-size:12px}
.big{font-size:30px;font-weight:680;letter-spacing:-.02em;line-height:1.1}
.up{color:var(--ok)}.down{color:var(--bad)}
/* budget */
.bud .ln{display:grid;grid-template-columns:minmax(110px,1.2fr) 2fr auto;gap:12px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line)}
.bud .ln:last-of-type{border-bottom:0}.bud .bl{font-size:13.5px}.bud .bl small{display:block;color:var(--faint);font-size:11.5px}
.bud .amt{font:600 13.5px ui-monospace,Menlo,monospace;text-align:right;min-width:78px}
input[type=range]{width:100%;accent-color:var(--accent)}
.stack{display:flex;height:10px;border-radius:999px;overflow:hidden;margin:12px 0 8px;background:var(--line)}
.stack i{display:block;height:100%}
.legend2{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--muted)}.legend2 i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px}
.ppl{display:inline-flex;align-items:center;gap:6px;font-size:13px}.ppl button{width:24px;height:24px;border-radius:50%;border:1px solid var(--line);background:var(--surface2);color:var(--fg);cursor:pointer}
.capbar{height:6px;border-radius:999px;background:var(--line);overflow:hidden;margin-top:6px}.capbar i{display:block;height:100%;background:var(--ok)}
/* calculator */
.calc{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:560px){.calc{grid-template-columns:1fr}}
.cin label{display:flex;justify-content:space-between;font-size:12.5px;color:var(--muted);margin:6px 0 2px}
.cin input[type=number]{width:96px;border:1px solid var(--line);background:var(--surface2);color:var(--fg);border-radius:7px;padding:2px 6px;font:600 12.5px ui-monospace,Menlo,monospace;text-align:right}
.cout .o{padding:8px 0;border-bottom:1px solid var(--line)}.cout .o:last-child{border:0}.cout .o .v{font-size:22px;font-weight:660}.cout .o.main .v{font-size:30px}
/* weather */
.wx .now{display:flex;align-items:center;gap:14px}.wx .ico{font-size:44px;line-height:1}
.wx .days{display:grid;grid-template-columns:repeat(auto-fit,minmax(74px,1fr));gap:6px;margin-top:12px}
.wx .day{background:var(--surface2);border-radius:12px;padding:8px 6px;text-align:center;font-size:12.5px}.wx .day b{display:block;font-size:12px;color:var(--muted);font-weight:600}.wx .day .e{font-size:22px;margin:2px 0}
.spark{width:100%;height:64px;display:block;margin-top:8px}
/* stocks */
.stk+.stk{margin-top:10px}.rtabs{display:flex;gap:4px}.rtabs button{border:0;background:transparent;color:var(--muted);font:600 12px inherit;padding:3px 8px;border-radius:7px;cursor:pointer}.rtabs button.on{background:var(--surface2);color:var(--fg)}
.r52{position:relative;height:4px;border-radius:999px;background:var(--line);margin:4px 0 2px}.r52 i{position:absolute;top:-3px;width:10px;height:10px;border-radius:50%;background:var(--fg);transform:translateX(-50%)}
.tip{position:absolute;pointer-events:none;background:var(--surface2);border:1px solid var(--line);border-radius:8px;padding:3px 7px;font-size:11.5px;box-shadow:var(--shadow);display:none;white-space:nowrap}
/* link previews */
.lp{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.lpc{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;cursor:pointer;display:flex;flex-direction:column;transition:transform .15s}
.lpc:hover{transform:translateY(-2px)}.lpc .ph{aspect-ratio:16/10;border-radius:0}
.lpc .bd{padding:9px 11px 11px}.lpc .site{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--faint)}.lpc .site img{width:13px;height:13px;border-radius:3px}
.lpc .tt{font-weight:620;font-size:13.5px;margin:3px 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.lpc .ds{font-size:12.5px;color:var(--muted);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.lpc .rd{font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);margin-top:8px;padding-top:8px;display:none}.lpc .rd p{margin:0 0 6px}
.lpc.open .rd{display:block}.lpc .rb{margin-top:6px;border:0;background:transparent;color:var(--accent);font:600 12px inherit;cursor:pointer;padding:0}
/* email draft, files, status, apps */
.mail .hd{font-size:13px;color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:8px;margin-bottom:8px}.mail .hd b{color:var(--fg);font-weight:600}
.mail .bdy{white-space:pre-wrap;font-size:14px}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--surface2);color:var(--fg);border-radius:10px;padding:6px 12px;font:600 13px inherit;cursor:pointer}
.btn.pri{background:var(--fg);color:var(--surface2);border-color:var(--fg)}.btn:hover{filter:brightness(1.06)}
.file{display:flex;gap:14px;align-items:center}
.fprev{display:block;max-width:100%;max-height:420px;margin-top:12px;border-radius:10px;border:1px solid var(--line);background:#fff;cursor:pointer}
.fex{margin-top:10px}.fex summary{cursor:pointer;font-size:12.5px;color:var(--muted)}.fex pre{white-space:pre-wrap;font:12.5px/1.5 ui-monospace,Menlo,monospace;background:var(--surface2);border-radius:10px;padding:10px;margin-top:6px;max-height:260px;overflow:auto}.file .fi{width:52px;height:64px;border-radius:9px;display:flex;align-items:center;justify-content:center;font:700 12px ui-monospace,Menlo,monospace;color:#fff;flex:none}
.sts{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px}
.sti{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:9px 11px}.sti .n{font-weight:600;font-size:13px;display:flex;align-items:center;gap:7px}
.sti .n i{width:8px;height:8px;border-radius:50%;flex:none}.sti .d{font-size:12px;color:var(--muted);margin-top:2px}.sti .v{font:600 13px ui-monospace,Menlo,monospace;margin-top:3px}
.apps{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.app{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:11px;cursor:pointer;transition:transform .15s}.app:hover{transform:translateY(-2px)}
.app .e{font-size:24px}.app .n{font-weight:640;font-size:13.5px;margin-top:4px}.app .d{font-size:12px;color:var(--muted)}
/* action bar */
.acts{display:flex;gap:6px;flex-wrap:wrap;align-items:center;position:relative}
.act{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:5px 11px;font:500 12.5px inherit;cursor:pointer}
.act:hover{color:var(--fg);background:var(--surface)}
.menu{position:absolute;z-index:5;bottom:36px;background:var(--surface2);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:5px;min-width:210px;display:none}
.menu.on{display:block}.menu button{display:flex;width:100%;align-items:center;gap:8px;border:0;background:transparent;color:var(--fg);padding:7px 9px;border-radius:8px;font:500 13px inherit;cursor:pointer;text-align:left}
.menu button:hover{background:var(--surface)}.menu small{color:var(--faint);margin-left:auto}
.toast{position:fixed;left:50%;bottom:12px;transform:translateX(-50%);background:var(--fg);color:var(--surface2);padding:6px 12px;border-radius:999px;font-size:12.5px;z-index:9;opacity:0;transition:opacity .2s}
.toast.on{opacity:1}
</style>
<script nonce="__NONCE__">
(function(){
"use strict";
var I=window.IUI;var h=I.h,txt=I.txt,arr=I.arr,md=I.md,photo=I.photo,label=I.label,icon=I.icon,UI=I.UI,X=I.X;
var COLORS=['#4f8ef7','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16'];
function num(v,d){v=+v;return isFinite(v)?v:(d||0);}
function money(v,cur,dec){cur=cur==null?'$':cur;var n=Math.abs(v);var s=n.toLocaleString(undefined,{minimumFractionDigits:dec||0,maximumFractionDigits:dec==null?0:dec});return (v<0?'−':'')+cur+s;}
function toast(t){var e=document.querySelector('.toast');if(!e){e=h('div','toast');document.body.appendChild(e);}e.textContent=t;e.classList.add('on');clearTimeout(e._t);e._t=setTimeout(function(){e.classList.remove('on');},1600);}
function copyText(t){function fb(){var ta=document.createElement('textarea');ta.value=t;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();var ok=false;try{ok=document.execCommand('copy');}catch(e){}ta.remove();return ok;}
 if(navigator.clipboard&&navigator.clipboard.writeText){return navigator.clipboard.writeText(t).then(function(){return true;},function(){return fb();});}return Promise.resolve(fb());}
I.toast=toast;I.copyText=copyText;
function svgEl(tag,a){var e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(var k in a)e.setAttribute(k,a[k]);return e;}
/* area sparkline with hover tooltip; pts=[[x,y],...] */
function spark(pts,opt){opt=opt||{};var W=600,H=opt.h||90;var wrap=h('div','');wrap.style.position='relative';if(pts.length<2)return wrap;
 var xs=pts.map(function(p){return p[0];}),ys=pts.map(function(p){return p[1];});var x0=Math.min.apply(null,xs),x1=Math.max.apply(null,xs),y0=Math.min.apply(null,ys),y1=Math.max.apply(null,ys);if(y1===y0){y1+=1;y0-=1;}
 var pad=4;var X=function(x){return (x-x0)/((x1-x0)||1)*W;},Y=function(y){return pad+(1-(y-y0)/(y1-y0))*(H-2*pad);};
 var col=opt.color||'#4f8ef7';var svg=svgEl('svg',{viewBox:'0 0 '+W+' '+H,preserveAspectRatio:'none','class':'spark'});svg.style.height=H*0.8+'px';
 var gid='g'+Math.random().toString(36).slice(2,8);var defs=svgEl('defs',{});var lg=svgEl('linearGradient',{id:gid,x1:0,y1:0,x2:0,y2:1});lg.appendChild(svgEl('stop',{offset:'0%','stop-color':col,'stop-opacity':.28}));lg.appendChild(svgEl('stop',{offset:'100%','stop-color':col,'stop-opacity':0}));defs.appendChild(lg);svg.appendChild(defs);
 var d=pts.map(function(p,i){return (i?'L':'M')+X(p[0]).toFixed(1)+' '+Y(p[1]).toFixed(1);}).join(' ');
 svg.appendChild(svgEl('path',{d:d+' L'+W+' '+H+' L0 '+H+' Z',fill:'url(#'+gid+')'}));svg.appendChild(svgEl('path',{d:d,fill:'none',stroke:col,'stroke-width':2,'vector-effect':'non-scaling-stroke'}));
 if(opt.base!=null&&opt.base>y0&&opt.base<y1){svg.appendChild(svgEl('line',{x1:0,x2:W,y1:Y(opt.base),y2:Y(opt.base),stroke:'currentColor','stroke-opacity':.25,'stroke-dasharray':'4 4','vector-effect':'non-scaling-stroke'}));}
 var dot=svgEl('circle',{r:4,fill:col,cx:-10,cy:-10});svg.appendChild(dot);wrap.appendChild(svg);var tip=h('div','tip');wrap.appendChild(tip);
 svg.addEventListener('mousemove',function(e){var r=svg.getBoundingClientRect();var fx=(e.clientX-r.left)/r.width*W;var best=0,bd=1e18;pts.forEach(function(p,i){var dd=Math.abs(X(p[0])-fx);if(dd<bd){bd=dd;best=i;}});var p=pts[best];
  dot.setAttribute('cx',X(p[0]));dot.setAttribute('cy',Y(p[1]));tip.style.display='block';tip.textContent=(opt.fmtX?opt.fmtX(p[0]):p[0])+'  ·  '+(opt.fmtY?opt.fmtY(p[1]):p[1]);var px=X(p[0])/W*r.width;tip.style.left=Math.min(r.width-tip.offsetWidth,Math.max(0,px-tip.offsetWidth/2))+'px';tip.style.top='-6px';});
 svg.addEventListener('mouseleave',function(){tip.style.display='none';dot.setAttribute('cx',-10);});return wrap;}
I.spark=spark;
/* ---------- budget ---------- */
X.budget=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var cur=b.currency==null?'$':b.currency;var p=h('div','panel bud');w.appendChild(p);
 var people=b.people?Math.max(1,num(b.people,1)):0;var items=arr(b.items).filter(Boolean).map(function(it,i){var a=num(it.amount);var mn=it.min!=null?num(it.min):Math.round(a*0.4);var mx=it.max!=null?num(it.max):Math.max(Math.round(a*2),a+10);return {it:it,v:a,min:mn,max:mx,step:num(it.step,(mx-mn)>200?10:1),color:it.color||COLORS[i%COLORS.length]};});
 var head=h('div','row2');var tl=h('div','');tl.appendChild(txt('div','faint','Estimated total'));var tot=txt('div','big','');tl.appendChild(tot);var pp=txt('div','faint','');tl.appendChild(pp);head.appendChild(tl);
 var ppl=null,pv=null;if(people){ppl=h('div','ppl');var m=txt('button','','−'),pl=txt('button','','+');pv=txt('b','',people+' people');ppl.appendChild(m);ppl.appendChild(pv);ppl.appendChild(pl);m.onclick=function(){people=Math.max(1,people-1);upd();};pl.onclick=function(){people=Math.min(50,people+1);upd();};head.appendChild(ppl);}
 p.appendChild(head);var stack=h('div','stack');p.appendChild(stack);var leg=h('div','legend2');p.appendChild(leg);var capWrap=null,capTxt=null,capBar=null;
 if(b.cap){capWrap=h('div','');capWrap.style.marginTop='8px';capTxt=txt('div','faint','');capBar=h('div','capbar',[h('i')]);capWrap.appendChild(capTxt);capWrap.appendChild(capBar);p.appendChild(capWrap);}
 var list=h('div','');list.style.marginTop='10px';p.appendChild(list);
 items.forEach(function(x){var ln=h('div','ln');var lb=h('div','bl');lb.appendChild(document.createTextNode((x.it.icon?x.it.icon+' ':'')+(x.it.label||'')));var sub=txt('small','','');lb.appendChild(sub);ln.appendChild(lb);
  var r=document.createElement('input');r.type='range';r.min=x.min;r.max=x.max;r.step=x.step;r.value=x.v;r.oninput=function(){x.v=+r.value;upd();};ln.appendChild(r);var a=txt('div','amt','');ln.appendChild(a);x.sub=sub;x.amt=a;list.appendChild(ln);});
 function sub(x){var q=num(x.it.qty,1);var mult=(x.it.per_person&&people)?people:1;return x.v*q*mult;}
 function upd(){var t=0;items.forEach(function(x){t+=sub(x);});tot.textContent=money(t,cur);pp.textContent=people?money(t/people,cur)+' per person':(b.note||'');if(pv)pv.textContent=people+(people===1?' person':' people');
  stack.innerHTML='';leg.innerHTML='';items.forEach(function(x){var s=sub(x);var seg=h('i');seg.style.width=(t?s/t*100:0)+'%';seg.style.background=x.color;seg.title=(x.it.label||'')+': '+money(s,cur);stack.appendChild(seg);var lg=h('span');var dot=h('i');dot.style.background=x.color;lg.appendChild(dot);lg.appendChild(document.createTextNode((x.it.label||'')+' '+Math.round(t?s/t*100:0)+'%'));leg.appendChild(lg);
   var q=num(x.it.qty,1);x.sub.textContent=(q!==1||x.it.unit?money(x.v,cur)+(x.it.unit?' / '+x.it.unit:'')+(q!==1?' × '+q:''):'')+(x.it.per_person&&people?' × '+people+' ppl':'');x.amt.textContent=money(s,cur);});
  if(capWrap){var c=num(b.cap);var left=c-t;capTxt.innerHTML='';capTxt.appendChild(document.createTextNode('Budget '+money(c,cur)+' · '));var s2=txt('b',left>=0?'up':'down',left>=0?money(left,cur)+' left':money(-left,cur)+' over');capTxt.appendChild(s2);var bar=capBar.firstChild;bar.style.width=Math.min(100,t/c*100)+'%';bar.style.background=left>=0?'var(--ok)':'var(--bad)';}}
 upd();return w;};
'''
_HTML += r'''/* ---------- calculator: safe expression parser (no eval) ---------- */
var FN={min:Math.min,max:Math.max,abs:Math.abs,sqrt:Math.sqrt,pow:Math.pow,exp:Math.exp,ln:Math.log,log:function(x){return Math.log10(x);},floor:Math.floor,ceil:Math.ceil,
 round:function(x,d){var m=Math.pow(10,d||0);return Math.round(x*m)/m;},clamp:function(x,a,b){return Math.min(b,Math.max(a,x));},
 pmt:function(r,n,pv){return r?pv*r/(1-Math.pow(1+r,-n)):pv/n;},fv:function(r,n,pmt,pv){pv=pv||0;return r?pv*Math.pow(1+r,n)+pmt*(Math.pow(1+r,n)-1)/r:pv+pmt*n;},
 pv:function(r,n,pmt){return r?pmt*(1-Math.pow(1+r,-n))/r:pmt*n;},iff:function(c,a,b){return c?a:b;}};
function compile(src){var s=String(src||''),i=0;var toks=[];var re=/\s*(?:(\d+\.?\d*(?:e[+-]?\d+)?|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|(<=|>=|==|!=|[-+*\/^%(),<>]))/y;
 while(i<s.length){re.lastIndex=i;var m=re.exec(s);if(!m){if(/^\s*$/.test(s.slice(i)))break;throw new Error('bad char at '+i);}i=re.lastIndex;toks.push(m[1]!=null?{n:+m[1]}:m[2]!=null?{id:m[2]}:{op:m[3]});}
 var p=0;function peek(o){return toks[p]&&toks[p].op===o;}function take(o){if(!peek(o))throw new Error('expected '+o);p++;}
 function cmp(){var a=add();while(toks[p]&&/^(<|>|<=|>=|==|!=)$/.test(toks[p].op||'')){var o=toks[p++].op,b=add();a=(function(a,b,o){return function(v){var x=a(v),y=b(v);return +(o==='<'?x<y:o==='>'?x>y:o==='<='?x<=y:o==='>='?x>=y:o==='=='?x===y:x!==y);};})(a,b,o);}return a;}
 function add(){var a=mul();while(peek('+')||peek('-')){var o=toks[p++].op,b=mul();a=(function(a,b,o){return o==='+'?function(v){return a(v)+b(v);}:function(v){return a(v)-b(v);};})(a,b,o);}return a;}
 function mul(){var a=pw();while(peek('*')||peek('/')||peek('%')){var o=toks[p++].op,b=pw();a=(function(a,b,o){return o==='*'?function(v){return a(v)*b(v);}:o==='/'?function(v){return a(v)/b(v);}:function(v){return a(v)%b(v);};})(a,b,o);}return a;}
 function pw(){var a=un();if(peek('^')){p++;var b=pw();return function(v){return Math.pow(a(v),b(v));};}return a;}
 function un(){if(peek('-')){p++;var a=un();return function(v){return -a(v);};}if(peek('+')){p++;return un();}return prim();}
 function prim(){var t=toks[p++];if(!t)throw new Error('unexpected end');if(t.n!=null){var n=t.n;return function(){return n;};}
  if(t.op==='('){var e=cmp();take(')');return e;}
  if(t.id){var id=t.id;if(peek('(')){p++;var args=[];if(!peek(')')){args.push(cmp());while(peek(',')){p++;args.push(cmp());}}take(')');var f=FN[id==='if'?'iff':id];if(!f)throw new Error('unknown function '+id);return function(v){return f.apply(null,args.map(function(a){return a(v);}));};}
   if(id==='pi')return function(){return Math.PI;};return function(v){if(!(id in v))throw new Error('unknown '+id);return v[id];};}
  throw new Error('unexpected '+(t.op||''));}
 var f=cmp();if(p<toks.length)throw new Error('unexpected '+(toks[p].op||toks[p].id||toks[p].n));return f;}
I.compile=compile;
function fmtVal(v,f,cur,dec){if(!isFinite(v))return '—';if(f==='money')return money(v,cur,dec==null?(Math.abs(v)<100?2:0):dec);if(f==='percent')return (+v).toFixed(dec==null?2:dec)+'%';if(f==='years')return (+v).toFixed(dec==null?1:dec)+' yrs';
 return (+v).toLocaleString(undefined,{maximumFractionDigits:dec==null?2:dec});}
X.calculator=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var cur=b.currency==null?'$':b.currency;var p=h('div','panel calc');w.appendChild(p);
 var cin=h('div','cin'),cout=h('div','cout');p.appendChild(cin);p.appendChild(cout);var vals={};
 arr(b.inputs).forEach(function(inp){if(!inp||!inp.id)return;var v=num(inp.value);vals[inp.id]=v;var mn=inp.min!=null?num(inp.min):0,mx=inp.max!=null?num(inp.max):Math.max(10,v*3),st=inp.step!=null?num(inp.step):((mx-mn)/200>=1?Math.round((mx-mn)/200):((mx-mn)/200));
  var lab=h('label');lab.appendChild(document.createTextNode(inp.label||inp.id));var nb=document.createElement('input');nb.type='number';nb.value=v;nb.step=st;lab.appendChild(nb);cin.appendChild(lab);
  var r=document.createElement('input');r.type='range';r.min=mn;r.max=mx;r.step=st||'any';r.value=v;cin.appendChild(r);
  r.oninput=function(){vals[inp.id]=+r.value;nb.value=r.value;run();};nb.oninput=function(){var x=+nb.value;if(isFinite(x)){vals[inp.id]=x;if(x>=mn&&x<=mx)r.value=x;run();}};});
 var outs=arr(b.outputs).filter(function(o){return o&&o.expr;}).map(function(o,i){var el=h('div','o'+(i===0?' main':''));el.appendChild(txt('div','faint',o.label||''));var v=txt('div','v','');el.appendChild(v);if(o.note)el.appendChild(txt('div','faint',o.note));cout.appendChild(el);var f=null,err=null;try{f=compile(o.expr);}catch(e){err=e.message;}return {o:o,v:v,f:f,err:err};});
 function run(){var scope=Object.assign({},vals);outs.forEach(function(x){if(!x.f){x.v.textContent='⚠ '+x.err;return;}var r;try{r=x.f(scope);}catch(e){x.v.textContent='⚠ '+e.message;return;}if(x.o.id)scope[x.o.id]=r;x.v.textContent=fmtVal(r,x.o.format,cur,x.o.decimals);});}
 run();return w;};
/* ---------- weather (Open-Meteo, resolved server-side) ---------- */
var DOW=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
X.weather=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var W=b.weather;var p=h('div','panel wx');w.appendChild(p);
 if(!W){p.appendChild(txt('div','muted','Weather for '+(b.location||'this place')+' is unavailable right now.'));return w;}
 var top=h('div','row2');var now=h('div','now');now.appendChild(txt('div','ico',W.now.icon));var nt=h('div','');nt.appendChild(txt('div','big',Math.round(W.now.t)+W.unit));nt.appendChild(txt('div','muted',W.now.text+' · feels '+Math.round(W.now.feels)+W.unit));now.appendChild(nt);top.appendChild(now);
 var rt=h('div','');rt.style.textAlign='right';rt.appendChild(txt('div','',W.label));rt.appendChild(txt('div','faint','💧 '+W.now.rh+'%  ·  💨 '+Math.round(W.now.wind)+' '+W.wind_unit));top.appendChild(rt);p.appendChild(top);
 var hr=arr(W.hourly).filter(function(x){return x.t!=null;});if(hr.length>2){p.appendChild(spark(hr.map(function(x,i){return [i,x.t];}),{h:70,color:'#f59e0b',fmtX:function(i){return hr[i].time;},fmtY:function(v){return Math.round(v)+W.unit+(hr[Math.round(0)]&&''||'');}}));}
 var ds=h('div','days');arr(W.daily).forEach(function(d,i){var c=h('div','day');var dt=new Date(d.date+'T12:00:00');c.appendChild(txt('b','',i===0?'Today':DOW[dt.getDay()]));c.appendChild(txt('div','e',d.icon));c.title=d.text+(d.sunrise?' · sunrise '+d.sunrise+' · sunset '+d.sunset:'');
  var t=h('div','');t.appendChild(txt('span','',Math.round(d.hi)+'°'));t.appendChild(txt('span','faint',' '+Math.round(d.lo)+'°'));c.appendChild(t);if(d.p!=null)c.appendChild(txt('div','faint','💧'+d.p+'%'));ds.appendChild(c);});p.appendChild(ds);
 p.appendChild(txt('div','faint','Live · '+W.source+' · updated '+new Date(W.fetched*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})));return w;};
/* ---------- stocks / crypto / commodities (Yahoo Finance chart API) ---------- */
X.stock=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));
 arr(b.quotes).forEach(function(q){var p=h('div','panel stk');w.appendChild(p);if(q.error||q.price==null){p.appendChild(txt('div','muted',q.symbol+': quote unavailable ('+(q.error||'no data')+')'));return;}
  var ch=q.prev?q.price-q.prev:0,pc=q.prev?ch/q.prev*100:0;var cls=ch>=0?'up':'down';var dec=q.price<2?4:2;
  var top=h('div','row2');var l=h('div','');var nm=h('div','');nm.appendChild(txt('b','',q.symbol));nm.appendChild(txt('span','faint','  '+q.name+(q.exchange?' · '+q.exchange:'')));l.appendChild(nm);
  var pr=h('div','');pr.appendChild(txt('span','big',q.price.toLocaleString(undefined,{minimumFractionDigits:dec,maximumFractionDigits:dec})));pr.appendChild(txt('span','faint',' '+q.currency));l.appendChild(pr);
  l.appendChild(txt('div',cls,(ch>=0?'▲ +':'▼ ')+ch.toFixed(dec)+' ('+(pc>=0?'+':'')+pc.toFixed(2)+'%) today'));top.appendChild(l);
  var tabs=h('div','rtabs');top.appendChild(tabs);p.appendChild(top);var chartBox=h('div','');p.appendChild(chartBox);
  var keys=['1D','1M','1Y'].filter(function(k){return arr((q.series||{})[k]).length>1;});var cur=keys[0];
  function draw(){chartBox.innerHTML='';var s=arr(q.series[cur]);var first=s[0][1],last=s[s.length-1][1];var up=cur==='1D'?ch>=0:last>=first;
   chartBox.appendChild(spark(s,{h:110,color:up?'#10b981':'#ef4444',base:cur==='1D'?q.prev:null,fmtX:function(t){var d=new Date(t*1000);return cur==='1D'?d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}):d.toLocaleDateString([],{month:'short',day:'numeric',year:cur==='1Y'?'2-digit':undefined});},fmtY:function(v){return v.toFixed(dec)+' '+q.currency;}}));
   tabs.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x.textContent===cur);});}
  keys.forEach(function(k){var bt=txt('button','',k);bt.onclick=function(){cur=k;draw();};tabs.appendChild(bt);});if(cur)draw();
  if(q.low52&&q.high52){var r=h('div','');r.style.marginTop='6px';var pos=Math.max(0,Math.min(100,(q.price-q.low52)/((q.high52-q.low52)||1)*100));var bar=h('div','r52',[h('i')]);bar.firstChild.style.left=pos+'%';
   var lbs=h('div','row2 faint');lbs.appendChild(txt('span','','52-wk low '+q.low52.toFixed(dec)));lbs.appendChild(txt('span','','high '+q.high52.toFixed(dec)));r.appendChild(bar);r.appendChild(lbs);p.appendChild(r);}
  p.appendChild(txt('div','faint','Delayed quote · '+q.source+' · '+(q.time?new Date(q.time*1000).toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'')+' · not investment advice'));});
 return w;};
'''
_HTML += r'''/* ---------- page preview cards ---------- */
X.links=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','lp');
 arr(b.items).forEach(function(it){if(!it||!it.url)return;var c=h('div','lpc');var img=it.shot||it.og_image;c.appendChild(photo({candidates:img?[{src:img}]:[],caption:''},'',{noText:true}));
  var bd=h('div','bd');var site=h('div','site');var fi=document.createElement('img');fi.src=I.fav(it.url);fi.alt='';fi.onerror=function(){fi.remove();};site.appendChild(fi);site.appendChild(document.createTextNode((it.site||I.domain(it.url))+(it.published?' · '+it.published:'')));bd.appendChild(site);
  bd.appendChild(txt('div','tt',it.title||I.domain(it.url)));if(it.description||it.note)bd.appendChild(txt('div','ds',it.note||it.description));
  var rd=arr(it.reader);if(rd.length){var box=h('div','rd');rd.forEach(function(t){box.appendChild(txt('p','',t));});var rb=txt('button','rb','Reader view');rb.onclick=function(e){e.stopPropagation();c.classList.toggle('open');rb.textContent=c.classList.contains('open')?'Hide reader':'Reader view';};bd.appendChild(rb);bd.appendChild(box);}
  c.appendChild(bd);c.addEventListener('click',function(e){if(!e.target.closest('.rb,.rd'))I.openLink(it.url);});g.appendChild(c);});
 w.appendChild(g);return w;};
/* ---------- Gmail draft ---------- */
function gmailUrl(o){var q='https://mail.google.com/mail/?view=cm&fs=1';if(o.to)q+='&to='+encodeURIComponent(o.to);if(o.cc)q+='&cc='+encodeURIComponent(o.cc);if(o.bcc)q+='&bcc='+encodeURIComponent(o.bcc);
 q+='&su='+encodeURIComponent(o.subject||'');var body=String(o.body||'');if(body.length>1800)body=body.slice(0,1790)+'\n…';return q+'&body='+encodeURIComponent(body);}
I.gmailUrl=gmailUrl;
X.email=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var p=h('div','panel mail');var hd=h('div','hd');
 [['To',b.to],['Cc',b.cc],['Subject',b.subject]].forEach(function(r){if(!r[1])return;var d=h('div','');d.appendChild(document.createTextNode(r[0]+': '));d.appendChild(txt('b','',r[1]));hd.appendChild(d);});p.appendChild(hd);p.appendChild(txt('div','bdy',b.body||''));
 var bt=h('div','btns');var g=h('button','btn pri',[icon('mail'),txt('span','','Open in Gmail')]);g.onclick=function(){I.openLink(gmailUrl(b));};bt.appendChild(g);
 var c=h('button','btn',[icon('copy'),txt('span','','Copy text')]);c.onclick=function(){copyText((b.subject?'Subject: '+b.subject+'\n\n':'')+(b.body||'')).then(function(){toast('Copied');});};bt.appendChild(c);
 var m=h('button','btn',[txt('span','','Other mail app')]);m.onclick=function(){var u='mailto:'+encodeURIComponent(b.to||'')+'?subject='+encodeURIComponent(b.subject||'')+'&body='+encodeURIComponent(String(b.body||'').slice(0,1800));try{parent.window.open(u,'_blank');}catch(e){window.open(u,'_blank');}};bt.appendChild(m);
 p.appendChild(bt);w.appendChild(p);return w;};
/* ---------- status board (e.g. homelab services reported by a status tool) ---------- */
var STC={ok:'#10b981',up:'#10b981',healthy:'#10b981',warn:'#f59e0b',warning:'#f59e0b',degraded:'#f59e0b',down:'#ef4444',error:'#ef4444',critical:'#ef4444',info:'#4f8ef7',unknown:'#8f8f8f'};
X.status=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var items=arr(b.items).filter(Boolean);var cnt={};items.forEach(function(s){var st=String(s.state||'unknown').toLowerCase();var k=/ok|up|healthy/.test(st)?'healthy':/warn|degraded/.test(st)?'warning':/down|error|critical/.test(st)?'down':'other';cnt[k]=(cnt[k]||0)+1;});
 w.appendChild(txt('div','faint',Object.keys(cnt).map(function(k){return cnt[k]+' '+k;}).join(' · ')+(b.updated?' · updated '+b.updated:'')));var g=h('div','sts');g.style.marginTop='6px';
 items.forEach(function(s){var c=h('div','sti');var n=h('div','n');var d=h('i');d.style.background=STC[String(s.state||'unknown').toLowerCase()]||STC.unknown;n.appendChild(d);n.appendChild(document.createTextNode(s.name||''));c.appendChild(n);if(s.detail)c.appendChild(txt('div','d',s.detail));if(s.value!=null)c.appendChild(txt('div','v',s.value));g.appendChild(c);});
 w.appendChild(g);return w;};
/* ---------- Craft apps launcher + file results ---------- */
function craftWeb(app){return UI.craft_web?UI.craft_web.replace(/\/$/,'')+'/'+app+'/':'';}
X.apps=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','apps');var list=arr(UI.apps);var only=arr(b.apps);
 list.filter(function(a){return !only.length||only.indexOf(a.id)>=0;}).forEach(function(a){var c=h('div','app');c.appendChild(txt('div','e',a.emoji));c.appendChild(txt('div','n',a.name));c.appendChild(txt('div','d',a.desc));c.title='Open '+a.name+' (web)';c.onclick=function(){I.openLink(craftWeb(a.id));};g.appendChild(c);});
 w.appendChild(g);var bt=h('div','btns');if(UI.craft_desktop){var d=h('button','btn pri',[icon('ext'),txt('span','','Craft desktop (all apps)')]);d.onclick=function(){I.openLink(UI.craft_desktop);};bt.appendChild(d);}
 if(UI.craft_web){var l=h('button','btn',[txt('span','','ArtCraft Launcher')]);l.onclick=function(){I.openLink(craftWeb('launcher'));};bt.appendChild(l);}w.appendChild(bt);return w;};
var FCOL={docx:'#2b579a',odt:'#2b579a',rtf:'#2b579a',pdf:'#d93025',xlsx:'#217346',csv:'#217346',pptx:'#d24726',gif:'#8b5cf6',md:'#555',html:'#e44d26'};
X.file=function(b){var w=h('div','blk');var p=h('div','panel');var f=h('div','file');var fi=txt('div','fi',String(b.format||'').toUpperCase());fi.style.background=FCOL[b.format]||'#555';f.appendChild(fi);
 var t=h('div','');t.appendChild(txt('div','',b.name||'file'));t.style.fontWeight='620';var meta=[b.size?(b.size>1e6?(b.size/1e6).toFixed(1)+' MB':Math.max(1,Math.round(b.size/1e3))+' KB'):'',b.maker?'made with '+b.maker:''].filter(Boolean).join(' · ');t.appendChild(txt('div','faint',meta));if(b.note)t.appendChild(txt('div','faint',b.note));if(b.mode==='read')t.appendChild(txt('div','faint','Opened with '+(b.app_name||'Craft')));if(b.opened)t.appendChild(txt('div','up','Opened in '+b.app_name+' on the Craft desktop'));f.appendChild(t);p.appendChild(f);
 if(b.preview){var pv=document.createElement('img');pv.src=b.preview;pv.alt='Preview of '+(b.name||'file');pv.className='fprev';pv.onclick=function(){I.openLink(b.url||'');};p.appendChild(pv);}
 if(b.excerpt){var ex=h('details','fex');ex.appendChild(txt('summary','','Contents'));ex.appendChild(txt('pre','',b.excerpt+(b.excerpt.length>=1500?'\n…':'')));p.appendChild(ex);}
 var bt=h('div','btns');if(b.url){var dl=h('button','btn pri',[icon('dl'),txt('span','','Download')]);dl.onclick=function(){I.openLink(b.url);};bt.appendChild(dl);}
 if(UI.craft_desktop&&b.app){var d=h('button','btn',[icon('ext'),txt('span','',(b.opened?'Go to ':'Open ')+(b.app_name||'Craft')+' desktop')]);d.onclick=function(){I.openLink(UI.craft_desktop);};bt.appendChild(d);}
 if(b.app&&craftWeb(b.app)){var wb=h('button','btn',[txt('span','',(b.app_name||'Craft')+' web')]);wb.title='Opens the web app; drag the downloaded file in';wb.onclick=function(){I.openLink(craftWeb(b.app));};bt.appendChild(wb);}
 p.appendChild(bt);if(b.inbox)p.appendChild(txt('div','faint','Also saved to ~/Inbox on the Craft desktop.'));w.appendChild(p);return w;};
X.note=function(b){var w=h('div','blk');var p=h('div','panel');var r=h('div','row2');var l=h('div','');l.appendChild(txt('div','faint','Saved to Notes'));l.appendChild(txt('div','',b.name||b.title||'Note'));l.firstChild.nextSibling.style.fontWeight='620';r.appendChild(l);
 if(b.url){var o=h('button','btn pri',[icon('note'),txt('span','','Open note')]);o.onclick=function(){I.openLink(b.url);};r.appendChild(o);}p.appendChild(r);w.appendChild(p);return w;};
'''
_HTML += r'''/* ---------- card -> markdown (copy, Gmail) ---------- */
function plain(s){return String(s==null?'':s).replace(/\[(\d{1,2})\]/g,'').replace(/\*\*([^*]+)\*\*/g,'$1');}
function cardText(S){var L=[];if(S.title)L.push('# '+S.title);if(S.subtitle)L.push(S.subtitle);
 arr(S.blocks).forEach(function(b){if(!b)return;var it=arr(b.items).filter(Boolean);if(b.title)L.push('\n## '+b.title);
  switch(b.type){case 'text':case 'quote':L.push(plain(b.md||b.text)+(b.by?'\n— '+b.by:''));break;case 'callout':L.push((b.title?b.title+': ':'')+plain(b.md));break;case 'hero':L.push(plain((b.title||'')+' '+(b.md||'')));break;
   case 'places':case 'cards':it.forEach(function(x){L.push('- '+(x.name||x.title||'')+[x.rating?' ★'+x.rating:'',x.price?' · '+x.price:''].join('')+(x.description?' — '+x.description:'')+(x.url?' ('+x.url+')':''));});break;
   case 'map':var d0=null;arr(b.places).forEach(function(p,i){if(p.day&&p.day!==d0){d0=p.day;L.push('\n'+p.day+':');}L.push((p.icon?p.icon+' ':'• ')+(p.name||'')+(p.time?' — '+p.time:'')+(p.note?': '+p.note:''));});var gm=I.gmapsUrl&&I.gmapsUrl(arr(b.places).filter(function(p){return p.lat!=null;}),(b.route_geo||{}).mode);if(gm)L.push('Route: '+gm);break;
   case 'timeline':it.forEach(function(x){L.push('- '+(x.time?x.time+' ':'')+(x.title||'')+(x.detail?' — '+x.detail:''));});break;
   case 'steps':it.forEach(function(x,i){L.push((i+1)+'. '+(x.title||x)+(x.detail?' — '+x.detail:''));});break;
   case 'table':L.push(arr(b.columns).join(' | '));arr(b.rows).forEach(function(r){L.push(arr(r).map(plain).join(' | '));});break;
   case 'stats':it.forEach(function(s){L.push('- '+s.label+': '+s.value+(s.delta?' ('+s.delta+')':''));});break;
   case 'compare':it.forEach(function(c){L.push(c.title+':');arr(c.points).forEach(function(p){L.push('  - '+p);});if(c.verdict)L.push('  → '+c.verdict);});break;
   case 'budget':var t=0,cur=b.currency==null?'$':b.currency;it.forEach(function(x){var s=num(x.amount)*num(x.qty,1)*((x.per_person&&b.people)?b.people:1);t+=s;L.push('- '+x.label+': '+money(s,cur));});L.push('Total: '+money(t,cur));break;
   case 'weather':if(b.weather){var W=b.weather;L.push(W.label+' now: '+Math.round(W.now.t)+W.unit+', '+W.now.text);arr(W.daily).forEach(function(d){L.push('- '+d.date+': '+d.text+' '+Math.round(d.hi)+'/'+Math.round(d.lo)+W.unit);});}break;
   case 'stock':arr(b.quotes).forEach(function(q){if(q.price!=null)L.push('- '+q.symbol+': '+q.price+' '+q.currency+(q.prev?' ('+((q.price-q.prev)/q.prev*100).toFixed(2)+'%)':''));});break;
   case 'links':it.forEach(function(x){L.push('- '+(x.title||x.url)+': '+x.url);});break;
   case 'email':L.push('To: '+(b.to||'')+'\nSubject: '+(b.subject||'')+'\n\n'+(b.body||''));break;
   case 'chart':arr(b.series).forEach(function(s){L.push('- '+s.name+': '+arr(b.labels).map(function(l,i){return l+'='+arr(s.data)[i];}).join(', '));});break;}});
 if(I.SRC.length){L.push('\nSources:');I.SRC.forEach(function(s,i){L.push((i+1)+'. '+(s.title||'')+' '+s.url);});}return L.join('\n').replace(/\n{3,}/g,'\n\n').trim();}
I.cardText=cardText;
/* ---------- calendar ---------- */
function pad(n){return (n<10?'0':'')+n;}
function parseWhen(date,time){var s=String(date||'');var m=s.match(/(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?/);if(!m)return null;var hh=m[4]!=null?+m[4]:null,mm=m[5]!=null?+m[5]:0;
 var t=String(time||'').match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?/i);if(hh==null&&t){hh=+t[1];mm=t[2]?+t[2]:0;var ap=(t[3]||'').toLowerCase();if(ap.indexOf('p')===0&&hh<12)hh+=12;if(ap.indexOf('a')===0&&hh===12)hh=0;}
 return {y:+m[1],mo:+m[2],d:+m[3],h:hh,mi:mm};}
function calStamp(w,addMin){if(w.h==null){var dt=new Date(Date.UTC(w.y,w.mo-1,w.d+(addMin?1:0)));return dt.getUTCFullYear()+pad(dt.getUTCMonth()+1)+pad(dt.getUTCDate());}
 var d=new Date(Date.UTC(w.y,w.mo-1,w.d,w.h,w.mi+(addMin||0)));return d.getUTCFullYear()+pad(d.getUTCMonth()+1)+pad(d.getUTCDate())+'T'+pad(d.getUTCHours())+pad(d.getUTCMinutes())+'00';}
function events(S){var ev=[];arr(S.events).forEach(function(e){if(!e)return;var s=parseWhen(e.start||e.date,e.time);if(!s)return;var en=e.end?parseWhen(e.end,e.end_time):null;ev.push({title:e.title||S.title,s:s,e:en,dur:num(e.duration_min,60),loc:e.location||'',det:e.details||''});});
 if(!ev.length)arr(S.blocks).forEach(function(b){if(b&&b.type==='timeline')arr(b.items).forEach(function(it){if(!it||!it.date)return;var s=parseWhen(it.date,it.time);if(s)ev.push({title:it.title||'',s:s,e:null,dur:num(it.duration_min,60),loc:it.place||it.location||'',det:it.detail||''});});});return ev;}
function gcal(e,tz){var st=calStamp(e.s,0),en=e.e?calStamp(e.e,0):calStamp(e.s,e.s.h==null?1:e.dur);return 'https://calendar.google.com/calendar/render?action=TEMPLATE&text='+encodeURIComponent(e.title)+'&dates='+st+'/'+en+(e.s.h!=null&&tz?'&ctz='+encodeURIComponent(tz):'')+(e.loc?'&location='+encodeURIComponent(e.loc):'')+(e.det?'&details='+encodeURIComponent(e.det):'');}
function ics(evs,tz){var esc=function(s){return String(s||'').replace(/([,;\\])/g,'\\$1').replace(/\n/g,'\\n');};var L=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Frontier UI//EN','CALSCALE:GREGORIAN'];
 evs.forEach(function(e,i){var st=calStamp(e.s,0),en=e.e?calStamp(e.e,0):calStamp(e.s,e.s.h==null?1:e.dur);var tzp=e.s.h!=null&&tz?';TZID='+tz:(e.s.h==null?';VALUE=DATE':'');L.push('BEGIN:VEVENT','UID:iui-'+Date.now()+'-'+i+'@frontier-ui','DTSTAMP:'+new Date().toISOString().replace(/[-:]/g,'').slice(0,15)+'Z','DTSTART'+tzp+':'+st,'DTEND'+tzp+':'+en,'SUMMARY:'+esc(e.title));if(e.loc)L.push('LOCATION:'+esc(e.loc));if(e.det)L.push('DESCRIPTION:'+esc(e.det));L.push('END:VEVENT');});
 L.push('END:VCALENDAR');return L.join('\r\n');}
function download(name,text,mime){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:mime}));a.download=name;document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},2000);}
/* ---------- action bar ---------- */
I.actions=function(S){if(S.actions===false||UI.actions===false)return null;var w=h('div','blk');var bar=h('div','acts');w.appendChild(bar);var title=S.title||'this card';var id=UI.card||'';var tz=S.timezone||(Intl.DateTimeFormat().resolvedOptions().timeZone)||'';
 function act(ic,lab,fn){var b=h('button','act',[icon(ic),txt('span','',lab)]);b.onclick=fn;bar.appendChild(b);return b;}
 function menu(anchor,items){var m=h('div','menu');items.forEach(function(it){var b=h('button','',[txt('span','',it[0])]);if(it[2])b.appendChild(txt('small','',it[2]));b.onclick=function(e){e.stopPropagation();m.classList.remove('on');it[1]();};m.appendChild(b);});bar.appendChild(m);
  anchor.onclick=function(e){e.stopPropagation();var on=!m.classList.contains('on');document.querySelectorAll('.menu.on').forEach(function(x){x.classList.remove('on');});if(on){m.style.left=anchor.offsetLeft+'px';m.classList.add('on');}};document.addEventListener('click',function(){m.classList.remove('on');});return m;}
 act('copy','Copy',function(){copyText(cardText(S)).then(function(ok){toast(ok?'Copied to clipboard':'Copy blocked by the browser');});});
 act('mail','Email',function(){I.openLink(gmailUrl({subject:title,body:cardText(S),to:S.email_to||''}));}).title='Compose in Gmail';
 var ev=events(S);if(ev.length){var cb=act('cal',ev.length>1?'Add to calendar ('+ev.length+')':'Add to calendar',null);if(ev.length===1){cb.onclick=function(){I.openLink(gcal(ev[0],tz));};}
  else{menu(cb,ev.slice(0,12).map(function(e){return [e.title,function(){I.openLink(gcal(e,tz));},e.s.mo+'/'+e.s.d+(e.s.h!=null?' '+pad(e.s.h)+':'+pad(e.s.mi):'')];}).concat([['Download all as .ics',function(){download((title||'events').replace(/[^\w -]+/g,'')+'.ics',ics(ev,tz),'text/calendar');},'Apple/Outlook']]));}}
 var ask=function(fmt,lab,open){I.sendPrompt('Export the Frontier UI card “'+title+'”'+(id?' (card id: '+id+')':'')+' as a '+lab+' file'+(open?' and open it in the Craft desktop':'')+'.');};
 var eb=act('doc','Export',null);eb.appendChild(icon('chev'));
 menu(eb,[['Word document',function(){ask('docx','Word (.docx)');},'.docx · WordCraft'],['PDF',function(){ask('pdf','PDF');},'.pdf'],['Excel spreadsheet',function(){ask('xlsx','Excel (.xlsx)');},'.xlsx · GridCraft'],['PowerPoint deck',function(){ask('pptx','PowerPoint (.pptx)');},'.pptx · DeckCraft'],['Open as a deck in DeckCraft',function(){ask('pptx','PowerPoint (.pptx)',true);},'desktop']]);
 act('note','Save to Notes',function(){I.sendPrompt('Save the Frontier UI card “'+title+'”'+(id?' (card id: '+id+')':'')+' to my Notes.');});
 return w;};
})();
</script>
'''


_HTML += r'''<script nonce="__NONCE__">
(function(){
"use strict";
var I=window.IUI;
var h=I.h,txt=I.txt,arr=I.arr,md=I.md,photo=I.photo,scroller=I.scroller,label=I.label,icon=I.icon,SVG=I.SVG,UI=I.UI;
var COLORS=['#4f8ef7','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16'];
var MAPS=[];/* registry: {places, select(name)} */
function words(s){return String(s||'').toLowerCase().split(/[^a-z0-9À-￿]+/).filter(function(w){return w.length>=4&&['temple','shrine','park','street','the','with','from','walk','tour','visit'].indexOf(w)<0;});}
function findPlace(name){name=String(name||'').toLowerCase().trim();if(!name)return null;var best=null,bs=0,qw=words(name);
 for(var i=0;i<MAPS.length;i++){var m=MAPS[i];for(var j=0;j<m.places.length;j++){var p=m.places[j];var n=String(p.name||'').toLowerCase();if(n===name||n.indexOf(name)>=0||name.indexOf(n)>=0)return {map:m,idx:j};
  var pw=words(n);var sc=qw.filter(function(w){return pw.some(function(x){return x===w||(w.length>=5&&x.indexOf(w.slice(0,5))===0);});}).length;if(sc>bs){bs=sc;best={map:m,idx:j};}}}
 return bs>=1?best:null;}
/* ---------- maplibre + local basemap loaders ---------- */
function loadScript(src){return new Promise(function(res,rej){var s=document.createElement('script');s.src=src;s.nonce=I.NONCE;s.onload=res;s.onerror=rej;document.head.appendChild(s);});}
var libP=null,localP=null,protoAdded=false;
function loadLib(){if(window.maplibregl)return Promise.resolve(window.maplibregl);if(libP)return libP;var T=UI.tiles;
 var local=T?loadScript(T+'/js/maplibre-gl.js').then(function(){var l=document.createElement('link');l.rel='stylesheet';l.href=T+'/js/maplibre-gl.css';document.head.appendChild(l);}):Promise.reject(0);
 libP=local.catch(function(){return loadScript(I.CDN+'/dist/maplibre-gl.js');}).then(function(){if(!window.maplibregl)throw new Error('maplibre missing');return window.maplibregl;});return libP;}
/* a self-hosted planet PMTiles (served on the LAN) when reachable; otherwise OpenFreeMap, then Esri raster */
function localBase(lib){if(localP)return localP;var T=UI.tiles;if(!T)return localP=Promise.resolve(false);
 var probe=fetch(T+'/planet.pmtiles',{headers:{Range:'bytes=0-126'}}).then(function(r){if(r.status!==206&&r.status!==200)throw 0;return Promise.all([window.pmtiles?0:loadScript(T+'/js/pmtiles.js'),window.basemaps?0:loadScript(T+'/js/basemaps.js')]);})
  .then(function(){if(!protoAdded){protoAdded=true;lib.addProtocol('pmtiles',new pmtiles.Protocol().tile);}return true;});
 localP=Promise.race([probe,new Promise(function(r){setTimeout(function(){r(false);},2500);})]).catch(function(){return false;});return localP;}
function lstyle(dark){var T=UI.tiles,fl=dark?'dark':'light';return {version:8,glyphs:T+'/fonts/{fontstack}/{range}.pbf',sprite:T+'/sprites/v4/'+fl,
 sources:{protomaps:{type:'vector',url:'pmtiles://'+T+'/planet.pmtiles',attribution:'© OpenStreetMap · Protomaps · self-hosted'}},layers:basemaps.layers('protomaps',basemaps.namedFlavor(fl),{lang:'en'})};}
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
function gmapsUrl(list,mode){list=list.slice(0,10);if(!list.length)return '';var ll=function(p){return (+p.lat).toFixed(6)+','+(+p.lng).toFixed(6);};
 if(list.length===1)return 'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(list[0].name?list[0].name+' '+ll(list[0]):ll(list[0]));
 var u='https://www.google.com/maps/dir/?api=1&origin='+ll(list[0])+'&destination='+ll(list[list.length-1]);if(list.length>2)u+='&waypoints='+encodeURIComponent(list.slice(1,-1).map(ll).join('|'));return u+'&travelmode='+(mode==='walk'?'walking':'driving');}
I.gmapsUrl=gmapsUrl;
function mapBlock(b){
 var places=arr(b.places).filter(function(p){return p&&p.lat!=null&&p.lng!=null&&isFinite(p.lat)&&isFinite(p.lng);});
 var wrap=h('div','blk');if(b.title)wrap.appendChild(label(b.title));
 if(!places.length){var l=h('div','maplist');arr(b.places).forEach(function(p){l.appendChild(txt('span','tag',(p.icon?p.icon+' ':'')+(p.name||'')));});wrap.appendChild(l);return wrap;}
 var days=arr(b.days_order).slice();if(!days.length){places.forEach(function(p){if(p.day&&days.indexOf(p.day)<0)days.push(p.day);});}if(days.length<2)days=[];
 var DR=b.day_routes||{};var dayColor=function(d){var i=days.indexOf(d);return i<0?null:COLORS[i%COLORS.length];};
 var curDay='';var tabs=null;
 if(days.length){tabs=h('div','dtabs');var mkTab=function(d,lab){var bt=h('button','dtab'+(d===''?' on':''));if(d){var dot=h('i');dot.style.background=dayColor(d);bt.appendChild(dot);}bt.appendChild(document.createTextNode(lab));bt.dataset.day=d;return bt;};
  tabs.appendChild(mkTab('','All days'));days.forEach(function(d){tabs.appendChild(mkTab(d,d));});wrap.appendChild(tabs);}
 var base=Math.min(560,Math.max(240,+b.height||380));var box=h('div','mapbox');box.style.height=base+'px';wrap.appendChild(box);
 var groups=[];if(!days.length)places.forEach(function(p){if(p.group&&groups.indexOf(p.group)<0)groups.push(p.group);});
 var ctlL=h('div','mctl l'),ctlR=h('div','mctl r');box.appendChild(ctlL);box.appendChild(ctlR);
 var sel=null;if(groups.length>1){sel=document.createElement('select');sel.className='mbtn';var o=document.createElement('option');o.value='';o.textContent='All groups';sel.appendChild(o);groups.forEach(function(g){var oo=document.createElement('option');oo.value=g;oo.textContent=g;sel.appendChild(oo);});ctlL.appendChild(sel);}
 var bFit=h('button','mbtn ic',[icon('nav')]);bFit.title='Fit all places';ctlL.appendChild(bFit);
 var bG=h('button','mbtn',[icon('ext'),txt('span','','Google Maps')]);bG.title='Open this route in Google Maps';ctlR.appendChild(bG);
 var bExp=h('button','mbtn',[icon('exp'),txt('span','','Expand')]);ctlR.appendChild(bExp);
 var pop=h('div','mpop');box.appendChild(pop);
 var stat=txt('div','mstat','');box.appendChild(stat);
 function visible(){return places.filter(function(p){return (!curDay||p.day===curDay)&&(!sel||!sel.value||p.group===sel.value);});}
 function routeFor(d){return d?DR[d]:(days.length?null:b.route_geo);}
 function setStat(){var rs=curDay?[DR[curDay]]:(days.length?days.map(function(d){return DR[d];}):[b.route_geo]);rs=rs.filter(function(r){return r&&r.km;});
  if(!rs.length){stat.style.display='none';return;}var km=0,mn=0;rs.forEach(function(r){km+=r.km;mn+=r.min;});var walk=rs[0].mode==='walk';
  stat.textContent=(walk?'🚶 ':'🚗 ')+fmtKm(km)+' · '+fmtMin(mn)+(walk?' walking':' by car')+' · '+visible().length+' stops'+(curDay?' · '+curDay:'');stat.style.display='block';}
 setStat();
 bG.onclick=function(){var r=routeFor(curDay)||b.route_geo||{};I.openLink(gmapsUrl(visible(),r.mode||b.mode));};
 var reg={places:places,select:function(){}};MAPS.push(reg);
 loadLib().then(function(lib){return localBase(lib).then(function(ok){return [lib,ok];});}).then(function(r){var lib=r[0],useLocal=r[1];
  var usedRaster=false;function styleFor(dark){return useLocal?lstyle(dark):vstyle(dark);}
  var map=new lib.Map({container:box,style:styleFor(I.isDark()),attributionControl:{compact:true},dragRotate:false,pitchWithRotate:false,cooperativeGestures:false,fadeDuration:150});
  box.dataset.base=useLocal?'local':'openfreemap';
  map.scrollZoom.disable();box.addEventListener('wheel',function(e){if(e.ctrlKey||e.metaKey){map.scrollZoom.enable();}else{map.scrollZoom.disable();}},{passive:true});
  function fallback(){if(useLocal){useLocal=false;box.dataset.base='openfreemap';map.setStyle(vstyle(I.isDark()));return;}if(!usedRaster){usedRaster=true;box.dataset.base='raster';map.setStyle(rstyle(I.isDark()));}}
  var failT=setTimeout(function(){if(!map.isStyleLoaded())fallback();},7000);
  map.on('error',function(){if(!map.isStyleLoaded())fallback();});
  var css=getComputedStyle(document.documentElement);
  function lines(){var out=[];if(days.length){days.forEach(function(d,i){var rg=DR[d];var ln=(rg&&rg.line&&rg.line.length>1)?rg.line:null;var pts=places.filter(function(p){return p.day===d;});if(!ln&&pts.length>1)ln=pts.map(function(p){return [p.lat,p.lng];});if(ln)out.push({id:'r'+i,day:d,line:ln,solid:!!(rg&&rg.line),color:COLORS[i%COLORS.length]});});}
   else{var rg=b.route_geo;var ln=(rg&&rg.line&&rg.line.length>1)?rg.line:(b.route?places.map(function(p){return [p.lat,p.lng];}):null);if(ln)out.push({id:'r0',day:'',line:ln,solid:!!(rg&&rg.line),color:css.getPropertyValue('--route').trim()||'#111'});}return out;}
  var LINES=lines();
  function addRoutes(){LINES.forEach(function(L){if(map.getSource(L.id))return;map.addSource(L.id,{type:'geojson',data:{type:'Feature',geometry:{type:'LineString',coordinates:L.line.map(function(c){return [c[1],c[0]];})}}});
    map.addLayer({id:L.id+'-case',type:'line',source:L.id,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':css.getPropertyValue('--routecase').trim()||'#fff','line-width':7,'line-opacity':.95}});
    map.addLayer({id:L.id,type:'line',source:L.id,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':L.color,'line-width':3.6,'line-dasharray':L.solid?[1,0]:[1.5,1.5]}});});showRoutes();}
  function showRoutes(){LINES.forEach(function(L){var v=(!curDay||L.day===curDay)?'visible':'none';[L.id,L.id+'-case'].forEach(function(id){if(map.getLayer(id))map.setLayoutProperty(id,'visibility',v);});});}
  map.on('styledata',function(){if(map.isStyleLoaded()){clearTimeout(failT);addRoutes();}});
  map.on('load',addRoutes);
  var mk=[];var dayIdx={};
  places.forEach(function(p,i){var el=h('div','pin');var n=p.day?(dayIdx[p.day]=(dayIdx[p.day]||0)+1):i+1;var dot=txt('div','dot',p.icon||String(n));var lab=txt('div','lab',p.name||'');
   var dc=dayColor(p.day);if(dc){dot.style.borderColor=dc;dot.style.boxShadow='0 0 0 2px '+dc+'55';}el.appendChild(dot);el.appendChild(lab);
   el.addEventListener('click',function(e){e.stopPropagation();choose(i,true);});
   var m=new lib.Marker({element:el,anchor:'top',offset:[0,-15]}).setLngLat([p.lng,p.lat]).addTo(map);mk.push({m:m,el:el,p:p});});
  function bounds(list){var bb=new lib.LngLatBounds();list.forEach(function(p){bb.extend([p.lng,p.lat]);});LINES.forEach(function(L){if((!curDay&&!(sel&&sel.value))||(curDay&&L.day===curDay))L.line.forEach(function(c){bb.extend([c[1],c[0]]);});});return bb;}
  function fit(list,anim){if(!list.length)return;if(list.length===1){map.jumpTo({center:[list[0].lng,list[0].lat],zoom:14});return;}map.fitBounds(bounds(list),{padding:{top:56,bottom:48,left:44,right:44},maxZoom:15,duration:anim?600:0});}
  fit(places,false);
  var cur=-1;
  function declutter(){var placed=[];var order=mk.map(function(o,j){return j;}).filter(function(j){return mk[j].el.style.display!=='none';});if(cur>=0&&order.indexOf(cur)>=0){order.splice(order.indexOf(cur),1);order.unshift(cur);}
   order.forEach(function(j){var o=mk[j];var pt=map.project([o.p.lng,o.p.lat]);var w=Math.min(220,(o.p.name||'').length*6.6+8);var r={x0:pt.x-w/2,x1:pt.x+w/2,y0:pt.y+2,y1:pt.y+20};var dot={x0:pt.x-15,x1:pt.x+15,y0:pt.y-15,y1:pt.y+15};
    var hit=placed.some(function(q){return !(r.x1<q.x0||r.x0>q.x1||r.y1<q.y0||r.y0>q.y1);});
    o.el.querySelector('.lab').style.visibility=hit?'hidden':'visible';placed.push(dot);if(!hit)placed.push(r);});}
  map.on('moveend',declutter);map.once('idle',declutter);setTimeout(declutter,50);
  function choose(i,fly){cur=i;mk.forEach(function(o,j){o.el.classList.toggle('sel',j===i);});var p=places[i];
   pop.innerHTML='';pop.appendChild(txt('b','',(p.icon?p.icon+'  ':'')+(p.name||'')));var meta=[p.day,p.time,p.note].filter(Boolean).join(' · ');if(meta)pop.appendChild(txt('span','',meta));
   var go=txt('a','mlink','Directions ↗');go.href='#';go.setAttribute('data-url',gmapsUrl([p]));pop.appendChild(go);pop.style.display='block';
   if(fly)map.easeTo({center:[p.lng,p.lat],zoom:Math.max(map.getZoom(),14),duration:600});
   declutter();document.dispatchEvent(new CustomEvent('iui-place',{detail:{name:p.name}}));}
  function applyFilter(){mk.forEach(function(o){var on=(!curDay||o.p.day===curDay);o.el.style.display=on?'':'none';o.el.classList.toggle('dim',!!(sel&&sel.value)&&o.p.group!==sel.value);});showRoutes();setStat();fit(visible(),true);setTimeout(declutter,650);}
  function setDay(d){curDay=d;if(tabs)tabs.querySelectorAll('.dtab').forEach(function(t){t.classList.toggle('on',t.dataset.day===d);});pop.style.display='none';applyFilter();document.dispatchEvent(new CustomEvent('iui-day',{detail:{day:d}}));}
  reg.select=function(i){var p=places[i];if(curDay&&p.day!==curDay)setDay(p.day);choose(i,true);box.scrollIntoView({block:'nearest',behavior:'smooth'});};
  map.on('click',function(){cur=-1;pop.style.display='none';mk.forEach(function(o){o.el.classList.remove('sel');});});
  bFit.onclick=function(){fit(visible(),true);};
  if(tabs)tabs.addEventListener('click',function(e){var t=e.target.closest('.dtab');if(t)setDay(t.dataset.day);});
  if(sel)sel.onchange=applyFilter;
  var big=false;bExp.onclick=function(){big=!big;box.style.height=(big?Math.max(560,Math.round(base*1.7)):base)+'px';bExp.innerHTML='';bExp.appendChild(icon(big?'col':'exp'));bExp.appendChild(txt('span','',big?'Collapse':'Expand'));setTimeout(function(){map.resize();fit(visible(),true);},380);};
  document.addEventListener('iui-theme',function(){usedRaster=false;map.setStyle(styleFor(I.isDark()));});
  new ResizeObserver(function(){map.resize();}).observe(box);
 }).catch(function(){box.style.height='auto';box.style.padding='12px';var l=h('div','maplist');places.forEach(function(p,i){l.appendChild(txt('span','tag',(p.icon||(i+1)+'.')+' '+p.name));});box.appendChild(l);});
 return wrap;}
'''
_HTML += r'''/* ---------- other blocks ---------- */
function images(b){var it=arr(b.items).slice(0,9);var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','gal'+(it.length>3?' scroll':' n'+it.length));
 it.forEach(function(x){g.appendChild(photo(x,'',{bookmark:true,caption:true,zoom:true}));});w.appendChild(it.length>3?scroller(g):g);return w;}
function stars(r){r=+r;if(!isFinite(r))return null;var s=h('span','');s.appendChild(txt('span','star','★ '));s.appendChild(document.createTextNode(r.toFixed(1)));return s;}
function priceLevel(p){var m=String(p||'').match(/[$€£¥₩]+/);if(m)return m[0].length;var n=parseFloat(String(p||'').replace(/[^0-9.]/g,''));return isFinite(n)?n:99;}
function places(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var items=arr(b.items).filter(Boolean);var row=h('div','cards');
 var cards=items.map(function(it,idx){var c=h('div','card'+(it.url?' link':''));c.appendChild(photo(it,'',{noText:true}));var cb=h('div','cb');cb.appendChild(txt('div','nm',it.name||it.title||''));
  var meta=h('div','meta');var bits=[];var st=stars(it.rating);if(st)bits.push(st);[it.price,it.subtitle].forEach(function(x){if(x)bits.push(document.createTextNode(String(x)));});
  bits.forEach(function(x,i){if(i)meta.appendChild(document.createTextNode(' · '));meta.appendChild(x);});if(bits.length)cb.appendChild(meta);
  if(it.description)cb.appendChild(txt('div','ds',it.description));
  var tg=arr(it.tags).slice(0,3);if(tg.length){var t=h('div','tags');tg.forEach(function(x){t.appendChild(txt('span','tag',x));});cb.appendChild(t);}
  c.appendChild(cb);c.addEventListener('click',function(){var f=findPlace(it.name);if(f&&!it.url){f.map.select(f.idx);return;}if(it.url)I.openLink(it.url);});
  return {el:c,it:it,idx:idx};});
 cards.forEach(function(c){row.appendChild(c.el);});
 /* interactive filters + sort (4+ items) */
 if(items.length>=4){var bar=h('div','fbar');var sort=document.createElement('select');sort.className='fsel';[['','Recommended'],['rating','Top rated'],['price','Price: low → high'],['price-','Price: high → low'],['name','Name A–Z']].forEach(function(o){var op=document.createElement('option');op.value=o[0];op.textContent=o[1];sort.appendChild(op);});bar.appendChild(sort);
  var tags={};items.forEach(function(it){arr(it.tags).forEach(function(t){tags[t]=(tags[t]||0)+1;});});var tagList=Object.keys(tags).sort(function(a,b){return tags[b]-tags[a];}).slice(0,8);
  var prices=[];items.forEach(function(it){var p=String(it.price||'').match(/^[$€£¥₩]{1,4}$/);if(p&&prices.indexOf(p[0])<0)prices.push(p[0]);});prices.sort(function(a,b){return a.length-b.length;});
  var active={tags:{},price:'',top:false};
  function chip(lab,on,cls){var c=txt('button','fchip'+(cls?' '+cls:''),lab);c.onclick=function(){on(c);apply();};return c;}
  prices.forEach(function(p){bar.appendChild(chip(p,function(){active.price=active.price===p?'':p;bar.querySelectorAll('.fchip.pr').forEach(function(x){x.classList.toggle('on',x.textContent===active.price);});},'pr'));});
  tagList.forEach(function(t){bar.appendChild(chip(t,function(c){active.tags[t]=!active.tags[t];c.classList.toggle('on',!!active.tags[t]);}));});
  if(items.some(function(it){return it.rating!=null;}))bar.appendChild(chip('★ 4.5+',function(c){active.top=!active.top;c.classList.toggle('on',active.top);}));
  var count=txt('span','fcount','');bar.appendChild(count);
  var apply=function(){var want=Object.keys(active.tags).filter(function(k){return active.tags[k];});var v=sort.value;var list=cards.slice();
   if(v==='rating')list.sort(function(a,b){return (+b.it.rating||0)-(+a.it.rating||0);});else if(v==='price')list.sort(function(a,b){return priceLevel(a.it.price)-priceLevel(b.it.price);});else if(v==='price-')list.sort(function(a,b){return priceLevel(b.it.price)-priceLevel(a.it.price);});else if(v==='name')list.sort(function(a,b){return String(a.it.name||'').localeCompare(String(b.it.name||''));});else list.sort(function(a,b){return a.idx-b.idx;});
   var shown=0;list.forEach(function(c){var ok=(!active.price||String(c.it.price||'')===active.price)&&want.every(function(t){return arr(c.it.tags).indexOf(t)>=0;})&&(!active.top||(+c.it.rating||0)>=4.5);c.el.style.display=ok?'':'none';if(ok)shown++;row.appendChild(c.el);});
   count.textContent=shown===items.length?'':shown+' of '+items.length;row.scrollLeft=0;row.dispatchEvent(new Event('scroll'));};
  sort.onchange=apply;w.appendChild(bar);}
 w.appendChild(scroller(row));return w;}
function timeline(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var tl=h('div','tl');
 arr(b.items).forEach(function(it){if(!it)return;var f=findPlace(it.place||it.title);var row=h('div','ti'+(f?' go':''));row.appendChild(txt('div','tm',it.time||''));var rail=h('div','rail',[h('div','bul')]);row.appendChild(rail);
  var body=h('div','tbody');if(it.candidates&&it.candidates.length){var th=h('div','thumb');th.appendChild(photo(it,'',{noText:true}));body.appendChild(th);}
  var tx=h('div','');tx.appendChild(txt('div','tt',it.title||''));if(it.detail)tx.appendChild(txt('div','td',it.detail));body.appendChild(tx);row.appendChild(body);
  row.dataset.day=it.day||(f&&f.map.places[f.idx].day)||'';
  if(f){row.addEventListener('click',function(){f.map.select(f.idx);});row.dataset.place=String(f.map.places[f.idx].name||'').toLowerCase();}
  tl.appendChild(row);});
 document.addEventListener('iui-place',function(e){var n=String(e.detail.name||'').toLowerCase();tl.querySelectorAll('.ti').forEach(function(r){r.classList.toggle('hl',!!n&&r.dataset.place===n);});});
 document.addEventListener('iui-day',function(e){var d=e.detail.day;tl.querySelectorAll('.ti').forEach(function(r){r.classList.toggle('off',!!d&&!!r.dataset.day&&r.dataset.day!==d);});});
 w.appendChild(tl);return w;}
function table(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var t=h('table');var th=h('thead'),tr=h('tr');var tb=h('tbody');var dir={};
 arr(b.columns).forEach(function(c,ci){var x=txt('th','',c);x.title='Sort';x.onclick=function(){dir[ci]=!dir[ci];var rows=Array.prototype.slice.call(tb.children);rows.sort(function(a,b){var A=a.children[ci]?a.children[ci].textContent:'',B=b.children[ci]?b.children[ci].textContent:'';var na=parseFloat(A.replace(/[^0-9.\-]/g,'')),nb=parseFloat(B.replace(/[^0-9.\-]/g,''));var r=(isFinite(na)&&isFinite(nb))?na-nb:A.localeCompare(B);return dir[ci]?r:-r;});rows.forEach(function(r){tb.appendChild(r);});};tr.appendChild(x);});th.appendChild(tr);t.appendChild(th);
 arr(b.rows).forEach(function(r){var row=h('tr');arr(r).forEach(function(c){var td=h('td');td.appendChild(md(c).firstChild||document.createTextNode(''));if(td.firstChild&&td.firstChild.tagName==='P'){td.innerHTML=td.firstChild.innerHTML;}row.appendChild(td);});tb.appendChild(row);});t.appendChild(tb);w.appendChild(h('div','tbl',[t]));return w;}
function stats(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','stats');arr(b.items).forEach(function(s){if(!s)return;var c=h('div','st');c.appendChild(txt('div','sl',s.label));c.appendChild(txt('div','sv',s.value));if(s.delta){var tone=s.tone||(/^\s*[-−]/.test(s.delta)?'down':'up');c.appendChild(txt('div','sd '+tone,s.delta));}g.appendChild(c);});w.appendChild(g);return w;}
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
var X=I.X||{};Object.keys(X).forEach(function(k){R[k]=X[k];});
/* ---------- render ---------- */
var S=I.S,app=I.app;
if(S.title)app.appendChild(txt('h1','t blk',S.title));if(S.subtitle)app.appendChild(txt('div','sub blk',S.subtitle));
var blocks=arr(S.blocks);var deferred=[];
blocks.forEach(function(b,i){if(b&&b.type==='map')deferred[i]=mapBlock(b);});
blocks.forEach(function(b,i){if(!b)return;var f=R[b.type]||text;var node;try{node=b.type==='map'?deferred[i]:f(b);}catch(e){node=txt('div','blk','['+b.type+' could not render]');}
 if(node){node.style.animationDelay=Math.min(i*60,420)+'ms';app.appendChild(node);}});
if(I.SRC.length){var sw=h('div','blk');sw.appendChild(txt('div','lbl','Sources'));var sr=h('div','srcs');I.SRC.forEach(function(s,i){var c=h('button','src');c.setAttribute('data-url',s.url);var d=h('div','d');var im=document.createElement('img');im.src=I.fav(s.url);im.alt='';im.onerror=function(){im.remove();};d.appendChild(im);d.appendChild(document.createTextNode((i+1)+'. '+I.domain(s.url)));c.appendChild(d);c.appendChild(txt('div','s',s.title||s.url));sr.appendChild(c);});sw.appendChild(sr);app.appendChild(sw);}
if(I.actions){try{var ab=I.actions(S,MAPS);if(ab)app.appendChild(ab);}catch(e){}}
var fu=arr(S.followups).filter(Boolean).slice(0,4);if(fu.length){var fw=h('div','blk');fw.appendChild(txt('div','lbl','Related'));var l=h('div','fu');fu.forEach(function(q){var bt=h('button','');bt.appendChild(icon('arrow'));bt.appendChild(document.createTextNode(String(q)));bt.onclick=function(){I.sendPrompt(String(q));};l.appendChild(bt);});fw.appendChild(l);app.appendChild(fw);}
document.querySelectorAll('.cite img').forEach(function(im){im.onerror=function(){im.remove();};});
setTimeout(I.reportHeight,50);
})();
</script>
</body>
</html>'''


class Tools:
    """Frontier UI: rich, ChatGPT-style visual answers (photos, maps, places, itineraries, charts, live data) plus real
    Word/Excel/PowerPoint/PDF files made, read and edited with all 15 ArtCraft apps, Gmail drafts and Open WebUI notes."""

    class Valves(BaseModel):
        searxng_url: str = Field(default="http://searxng:8080", description="SearXNG base URL used for image search (JSON format enabled).")
        maplibre_cdn: str = Field(default="https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1", description="MapLibre GL JS package base URL (fallback when tiles_url is not reachable).")
        tiles_url: str = Field(default="", description="Self-hosted basemap folder: planet.pmtiles, fonts/, sprites/v4/ and js/ (maplibre-gl, pmtiles, basemaps). Empty = OpenFreeMap.")
        resolve_images: bool = Field(default=True, description="Resolve photo queries to real images (Wikipedia + SearXNG).")
        resolve_maps: bool = Field(default=True, description="Geocode places and draw street routes (keyless OSM services).")
        live_data: bool = Field(default=True, description="Fetch live weather (Open-Meteo) and quotes (Yahoo Finance) for weather/stock blocks. Both are keyless.")
        temperature_unit: str = Field(default="fahrenheit", description="fahrenheit or celsius")
        embedding_url: str = Field(default="openwebui", description="'openwebui' = reuse Open WebUI's configured embedding engine (e.g. EmbeddingGemma) to rerank photos and link timeline rows to map pins; or an OpenAI-compatible base URL; empty = off.")
        embedding_model: str = Field(default="embeddinggemma-2", description="Embedding model name (only for a direct URL).")
        embedding_api_key: str = Field(default="", description="Bearer key (only for a direct URL).")
        craft_bridge_url: str = Field(default="", description="Craft bridge inside the Craft apps container, e.g. http://craft-apps:8790. Enables real .docx/.xlsx/.pptx/.pdf files and page screenshots.")
        craft_bridge_token: str = Field(default="", description="Shared token for the Craft bridge (X-Craft-Token).")
        craft_desktop_url: str = Field(default="", description="URL of the streamed Craft desktop (linuxserver/craft-apps), shown on file cards.")
        craft_web_url: str = Field(default="", description="Base URL of the self-hosted Craft web apps (…/wordcraft/, …/launcher/).")
        page_screenshots: bool = Field(default=True, description="Use headless Chromium (via the Craft bridge) for link preview screenshots.")

    def __init__(self):
        self.valves = self.Valves()

    # ---------------- helpers ----------------
    def _ui(self, card=""):
        v = self.valves
        return {"tiles": v.tiles_url.rstrip("/"), "craft_web": v.craft_web_url.rstrip("/"), "craft_desktop": v.craft_desktop_url, "card": card,
                "apps": [{"id": k, "name": n, "desc": d, "emoji": e} for k, (n, d, e) in CRAFT_APPS.items()] if v.craft_web_url or v.craft_desktop_url else []}

    def _bridge(self):
        v = self.valves
        return {"url": v.craft_bridge_url, "token": v.craft_bridge_token, "shots": v.page_screenshots} if v.craft_bridge_url and v.craft_bridge_token else None

    async def _card(self, spec, __event_call__, req=None):
        try:
            if req is not None:
                spec.setdefault("_ui", {})["base"] = str(req.base_url).rstrip("/")
        except Exception:
            pass
        theme = await _owui_theme(__event_call__)
        return HTMLResponse(content=_build_html(spec, theme, self.valves.maplibre_cdn, self.valves.tiles_url), headers={"Content-Disposition": "inline"})

    # ---------------- 1. rich card ----------------
    async def render_frontier_ui(self, spec: str, __event_emitter__=None, __event_call__=None, __request__=None) -> tuple:
        """
        Show a rich visual answer (ChatGPT-style generative UI) inside the chat. Use it whenever the answer has places, trips,
        itineraries, products, comparisons, numbers, prices, weather, stocks, links, timelines or anything that reads better with
        photos, a map, cards, a table, a chart or a calculator. You write ONE JSON object; the tool finds real photos, geocodes
        places, draws street routes, fetches live weather/quotes/page previews and renders it. Never invent image URLs: give photo
        SEARCH QUERIES. For places give the real name plus your best lat/lng; the tool verifies them. After the tool returns, reply
        with 1-2 sentences only (the card already shows everything); do not repeat its content or the JSON.

        spec = {"title": str, "subtitle": str?, "sources": [{"title","url"}]?, "blocks": [Block...], "followups": [str, 2-4],
                "events": [{"title","start":"2026-11-05T09:00","end"?,"location"?,"details"?}]?}   (events -> "Add to calendar")
        Blocks (use 3-7, in reading order; mix types, lead with text, put the most visual block early):
          {"type":"text","md":"markdown; **bold**, [link](url), cite sources inline as [1] [2]"}
          {"type":"images","items":[{"query":"Golden Gate Bridge from Baker Beach","caption":"Golden Gate"}]}  (3 specific queries)
          {"type":"map","area":"Kyoto, Japan","mode":"walk|drive","places":[{"name":"Fushimi Inari Taisha","lat":34.9671,"lng":135.7727,"icon":"⛩️","time":"8:00","note":"Go early"}]}
              (2-12 places in visiting order; street route drawn automatically; MULTI-DAY trips: use
               "days":[{"label":"Day 1","places":[...]},{"label":"Day 2","places":[...]}] instead of "places" -> day tabs, one coloured route per day)
          {"type":"places","area":"Kyoto","items":[{"name","subtitle","rating":4.6,"price":"$$","tags":["Ramen","Late night"],"description","url"?,"image":"photo query"?}]}
              (4+ items get sort/filter chips automatically - always give rating, price and 1-3 tags)
          {"type":"timeline","items":[{"time":"9:00 AM","date":"2026-11-05"?,"title","detail","place":"exact map place name"?,"day":"Day 1"?}]}
          {"type":"budget","currency":"$","people":2?,"cap":2500?,"items":[{"label":"Hotel","icon":"🏨","amount":180,"qty":3,"unit":"night","min":90,"max":400,"per_person":false}]}
              (interactive sliders; per_person items scale with the people stepper)
          {"type":"calculator","currency":"$","inputs":[{"id":"price","label":"Home price","value":450000,"min":100000,"max":1500000,"step":5000}],
              "outputs":[{"label":"Monthly payment","expr":"pmt(rate/100/12, years*12, price-down)","format":"money|percent|number|years","id":"pay"?}]}
              (expr: + - * / ^ % ( ) and min max round abs sqrt pow ln log exp floor ceil clamp pmt(rate,n,pv) fv(rate,n,pmt,pv) pv(rate,n,pmt) if(c,a,b); outputs may use earlier output ids)
          {"type":"weather","location":"Kyoto, Japan","days":5}            (LIVE forecast - never write numbers yourself)
          {"type":"stock","symbols":["AAPL","BTC-USD","GC=F"]}             (LIVE quotes + 1D/1M/1Y charts; Yahoo symbols; also crypto/commodities/FX like EURUSD=X)
          {"type":"links","items":[{"url":"https://...","note":"why it matters"?}]}   (page preview cards: screenshot, title, summary, reader view)
          {"type":"email","to"?,"cc"?,"subject","body"}                   (a ready-to-send draft with an "Open in Gmail" button)
          {"type":"status","items":[{"name","state":"ok|warn|down|info","detail","value"?}]}   (service/health boards, e.g. from a server-status tool)
          {"type":"apps"}                                                   (Craft apps launcher: WordCraft, GridCraft, DeckCraft, PhotoCraft...)
          {"type":"table","columns":["A","B"],"rows":[["1","2"]]}   {"type":"stats","items":[{"label","value","delta":"+4%"?}]}
          {"type":"chart","kind":"bar|line","labels":["2023","2024"],"series":[{"name","data":[1,2]}],"unit":"%"?}
          {"type":"callout","tone":"info|tip|warning|danger","title","md"}   {"type":"compare","items":[{"title","points":["..."],"verdict"?}]}
          {"type":"steps","items":[{"title","detail"}]}   {"type":"hero","image":"photo query","eyebrow","title","md"}   {"type":"quote","md","by"}
        Every card gets Copy, Email (Gmail), Export (Word/PDF/Excel/PowerPoint) and Save-to-Notes buttons automatically.
        Rules: concise, scannable copy; real facts only; cite with [n] only when sources are given; trips = images + map + timeline
        (+ budget when costs matter) with timeline "place" values matching map place names exactly.

        :param spec: The JSON object described above (as a JSON string).
        :return: An interactive rich embed rendered inline in the chat.
        """
        try:
            data = _loads_lenient(spec)
        except Exception as e:
            return f"Frontier UI could not parse spec JSON ({e}). Fix the JSON and call render_frontier_ui again."
        if isinstance(data, list):
            data = {"blocks": data}
        if not isinstance(data, dict):
            return "Frontier UI spec must be a JSON object with a blocks array."
        title = str(data.get("title") or "Response")[:120]
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Building “{title}”…", "done": False}})
        v = self.valves
        opts = {"live": v.live_data, "unit": "celsius" if v.temperature_unit.lower().startswith("c") else "fahrenheit", "bridge": self._bridge(),
                "embed": None}
        if v.embedding_url == "openwebui":
            fn = getattr(getattr(getattr(__request__, "app", None), "state", None), "EMBEDDING_FUNCTION", None)
            if fn:
                opts["embed"] = {"fn": fn}
        elif v.embedding_url:
            opts["embed"] = {"url": v.embedding_url, "model": v.embedding_model, "key": v.embedding_api_key}
        try:
            await asyncio.wait_for(_resolve(data, v.searxng_url, v.resolve_images, v.resolve_maps, opts), 14)
        except Exception:
            pass
        card = secrets.token_hex(4)
        data["_ui"] = self._ui(card)
        _CARDS[card] = data
        while len(_CARDS) > 300:
            _CARDS.pop(next(iter(_CARDS)))
        resp = await self._card(data, __event_call__, __request__)
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Showing “{title}”", "done": True}})
        kinds = [b.get("type") for b in data.get("blocks", []) if isinstance(b, dict)]
        return resp, (f"Frontier UI card “{title}” (card id: {card}) is rendered and visible to the user (blocks: {', '.join(map(str, kinds))}). "
                      "Reply with one or two short sentences that add context; do not repeat the card or show JSON. "
                      f"If the user later asks to export or save this card, call craft_file or save_note with card=\"{card}\".")

    # ---------------- 2. real Office files via the Craft apps ----------------
    async def craft_file(self, format: str, card: str = "", title: str = "", markdown: str = "", rows_json: str = "", slides_json: str = "",
                         open_in_desktop: bool = False, __user__: dict = None, __event_emitter__=None, __event_call__=None, __request__=None) -> tuple:
        """
        Create a real, downloadable file with the Craft apps (WordCraft / GridCraft / DeckCraft) and show a download card.
        Use it when the user asks for a Word document, PDF, Excel spreadsheet, PowerPoint deck, CSV, or to export / "make a file of"
        something - including "Export the Frontier UI card … (card id: X)" requests (then pass card="X" and nothing else).

        :param format: docx | pdf | odt | rtf | xlsx | csv | pptx  (Word, PDF, Excel, PowerPoint...)
        :param card: id of an earlier Frontier UI card to export (content, photos, charts and tables are reused automatically).
        :param title: file name / document title.
        :param markdown: document body in Markdown (docx/pdf/odt/rtf), or a slide outline for pptx ("# Slide title" + bullets).
        :param rows_json: for xlsx/csv: JSON array of rows, first row = header, e.g. [["Item","Cost"],["Hotel",420]].
        :param slides_json: for pptx: JSON array of slides [{"title","body":["bullet"],"image":"https://...jpg"?,"notes"?,"chart":{"type":"column|line|pie","categories":[...],"series":[{"name","values":[...]}]}?}]
        :param open_in_desktop: also open the file in the matching Craft app on the streamed Craft desktop.
        :return: A file card with Download and Open-in-Craft buttons.
        """
        fmt = str(format or "").lower().strip(". ")
        fmt = {"word": "docx", "excel": "xlsx", "powerpoint": "pptx", "ppt": "pptx", "doc": "docx", "xls": "xlsx"}.get(fmt, fmt)
        kind = FORMAT_KIND.get(fmt)
        if not kind or fmt in ("html", "md", "txt", "gif") and not markdown and not card:
            return f"Unsupported format '{format}'. Use docx, pdf, odt, rtf, xlsx, csv or pptx."
        spec = _CARDS.get(str(card).strip()) if card else None
        if card and not spec and not (markdown or rows_json or slides_json):
            return (f"Card {card} is no longer in memory (server restarted). Call craft_file again with the content itself: "
                    "markdown for documents, rows_json for spreadsheets or slides_json for decks.")
        name = re.sub(r"[^\w .()-]+", "", title or (spec or {}).get("title") or "Document").strip()[:80] or "Document"
        user = __user__ or {}
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Making {name}.{fmt} with {CRAFT_APPS[FORMAT_APP[kind]][0]}…", "done": False}})
        payload = {"kind": kind, "format": fmt, "name": name, "open": bool(open_in_desktop), "inbox": True}
        try:
            if kind == "doc":
                payload["markdown"] = markdown or _spec_md(spec or {"title": name})
            elif kind == "sheet":
                rows = json.loads(rows_json) if rows_json else _spec_rows(spec or {})
                if not rows:
                    return "No table-like content to put in a spreadsheet; pass rows_json."
                payload.update({"columns": [str(c) for c in rows[0]], "rows": rows[1:]})
            else:
                slides = json.loads(slides_json) if slides_json else (_spec_slides(spec) if spec else None)
                if slides:
                    payload["slides"] = slides
                else:
                    payload["markdown"] = markdown or f"# {name}"
        except Exception as e:
            return f"Could not read the content JSON ({e}). Fix it and call craft_file again."
        try:
            if fmt == "csv" and kind == "sheet" and not self._bridge():
                import csv as _csv
                buf = io.StringIO()
                _csv.writer(buf).writerows([payload["columns"]] + payload["rows"])
                res = {"name": f"{name}.csv", "mime": "text/csv", "b64": base64.b64encode(buf.getvalue().encode()).decode(), "app": "gridcraft"}
            else:
                async with aiohttp.ClientSession() as session:
                    res = await _bridge_call(session, self._bridge(), "/make", payload, 120)
            data = base64.b64decode(res["b64"])
            fid, url = await _store_file(user, res["name"], data, res.get("mime") or "application/octet-stream")
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": "File creation failed", "done": True}})
            return f"Creating the {fmt} file failed: {e}"
        app = res.get("app") or FORMAT_APP[kind]
        block = {"type": "file", "name": res["name"], "format": fmt, "size": len(data), "url": url, "app": app,
                 "app_name": CRAFT_APPS.get(app, (app,))[0], "maker": CRAFT_APPS[FORMAT_APP[kind]][0],
                 "opened": bool(res.get("opened")), "inbox": bool(res.get("path"))}
        ui = self._ui()
        ui["actions"] = False
        resp = await self._card({"blocks": [block], "_ui": ui}, __event_call__, __request__)
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"{res['name']} is ready", "done": True}})
        return resp, (f"The file {res['name']} ({len(data) // 1024 + 1} KB, made with {block['app_name']}) was created and a download card is shown"
                      + (" ; it is also open in the Craft desktop" if block["opened"] else "") + ". Reply with one short sentence; do not paste links.")

    # ---------------- 3. open anything in a Craft app ----------------
    async def craft_open(self, url: str, app: str = "", __event_emitter__=None, __event_call__=None, __request__=None) -> tuple:
        """
        Open a public image, PDF, SVG, audio or video URL in a Craft app on the streamed Craft desktop
        (PhotoCraft/LightCraft for photos, PdfCraft for PDFs, VectorCraft for SVG, FilmCraft for video, SoundCraft for audio).

        :param url: public http(s) URL of the file.
        :param app: optional app id: photocraft, lightcraft, pdfcraft, vectorcraft, filmcraft, soundcraft, wordcraft, gridcraft, deckcraft, cadcraft, solidcraft, figcraft, designcraft, effectcraft, craft-anything.
        :return: A card confirming where it opened.
        """
        try:
            async with aiohttp.ClientSession() as session:
                res = await _bridge_call(session, self._bridge(), "/open", {"url": url, "app": app.lower().strip()}, 60)
        except Exception as e:
            return f"Could not open it in a Craft app: {e}"
        a = res.get("app", "")
        ui = self._ui()
        ui["actions"] = False
        block = {"type": "file", "name": os.path.basename(res.get("path", "file")), "format": res.get("path", "").rsplit(".", 1)[-1],
                 "app": a, "app_name": CRAFT_APPS.get(a, (a,))[0], "opened": True, "inbox": True}
        resp = await self._card({"blocks": [block], "_ui": ui}, __event_call__, __request__)
        return resp, f"Opened in {block['app_name']} on the Craft desktop (saved to ~/Inbox). Reply with one short sentence."

    # ---------------- 4. Open WebUI notes ----------------
    async def save_note(self, title: str = "", markdown: str = "", card: str = "", __user__: dict = None, __event_call__=None, __request__=None) -> tuple:
        """
        Save something to the user's Open WebUI Notes. Use it for "save this", "add to my notes", "Save the Frontier UI card … to my Notes"
        (then pass card="<card id>").

        :param title: note title.
        :param markdown: note body in Markdown (optional when card is given).
        :param card: id of an Frontier UI card to save.
        :return: A card linking to the new note.
        """
        spec = _CARDS.get(str(card).strip()) if card else None
        body = markdown or (_spec_md(spec) if spec else "")
        if not body:
            return "Nothing to save: pass markdown, or a card id from this session."
        name = (title or (spec or {}).get("title") or body.strip().splitlines()[0].lstrip("# ") or "Note")[:120]
        try:
            nid = await _create_note(__user__ or {}, name, body)
        except Exception as e:
            return f"Saving the note failed: {e}"
        ui = self._ui()
        ui["actions"] = False
        resp = await self._card({"blocks": [{"type": "note", "name": name, "url": f"/notes/{nid}" if nid else ""}], "_ui": ui}, __event_call__, __request__)
        return resp, f"Saved to Notes as “{name}”. Reply with one short sentence."

    # ---------------- 5. read / edit / convert the user's own files with any ArtCraft app ----------------
    async def _file_card(self, block, __event_call__, req=None):
        ui = self._ui()
        ui["actions"] = False
        return await self._card({"blocks": [block], "_ui": ui}, __event_call__, req)

    async def craft_read(self, file: str = "", __user__: dict = None, __files__: list = None, __messages__: list = None,
                         __event_emitter__=None, __event_call__=None, __request__=None) -> tuple:
        """
        Open a file the user uploaded (or one made earlier in this chat) with the matching ArtCraft app and read it:
        Word/ODT/RTF (WordCraft), Excel/CSV with formulas (GridCraft), PowerPoint (DeckCraft), PDF (PdfCraft), images and PSD
        (PhotoCraft), RAW photos (LightCraft), SVG/AI/EPS (VectorCraft), DXF/DWG (CADCraft), STEP/STL/3MF (SolidCraft),
        Figma/Sketch/Penpot (FigCraft), IDML (DesignCraft), audio (SoundCraft), video (FilmCraft), EffectCraft projects, and any
        other file or app bundle (Craft Anything's first look). Use it before answering questions about an attached file or
        before editing it. Shows a preview card and returns the file's text, structure and metadata to you.

        :param file: file name (or part of it) or file id; empty = the most recently attached file.
        :return: A preview card; the extracted content is returned to you.
        """
        try:
            name, data, fid = await _load_file(file, __files__, __messages__, __user__)
        except Exception as e:
            return str(e)
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Reading {name}…", "done": False}})
        try:
            async with aiohttp.ClientSession() as session:
                r = await _bridge_call(session, self._bridge(), "/inspect", {"name": name, "b64": base64.b64encode(data).decode()}, 240)
        except Exception as e:
            return f"Could not read {name}: {e}"
        app = r.get("app", "")
        text, info = (r.get("text") or "").strip(), (r.get("info") or "").strip()
        block = {"type": "file", "name": name, "format": name.rsplit(".", 1)[-1].lower() if "." in name else "", "size": len(data),
                 "url": f"/api/v1/files/{fid}/content", "app": app, "app_name": CRAFT_APPS.get(app, (app,))[0], "mode": "read",
                 "preview": ("data:image/jpeg;base64," + r["preview"]) if r.get("preview") else "", "excerpt": text[:1500]}
        resp = await self._file_card(block, __event_call__, __request__)
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Read {name} with {block['app_name']}", "done": True}})
        ctx = [f"File “{name}” (id {fid}, {len(data) // 1024 + 1} KB) opened with {block['app_name']}. A preview card is shown."]
        if text:
            ctx.append("CONTENT:\n" + text[:14000] + ("\n…(truncated)" if len(text) > 14000 else ""))
        if r.get("formulas"):
            ctx.append("FORMULAS (CSV):\n" + r["formulas"][:4000])
        if info:
            ctx.append("STRUCTURE / METADATA:\n" + info[:5000])
        if app not in ("craft-anything",):
            ctx.append(f"To change it, call craft_edit(file=\"{name}\", commands_json=...) — look up {app} command ids with craft_commands(app=\"{app}\", search=...) first.")
        return resp, "\n\n".join(ctx)

    async def craft_edit(self, file: str = "", commands_json: str = "", replace_json: str = "", cells_json: str = "",
                         output_name: str = "", open_in_desktop: bool = False, __user__: dict = None, __files__: list = None,
                         __messages__: list = None, __event_emitter__=None, __event_call__=None, __request__=None) -> tuple:
        """
        Edit a file the user uploaded (or one made earlier) with its ArtCraft app, headlessly, and give back the edited copy as a
        download (the original is never changed). Works for Word/ODT/RTF, Excel/CSV, PowerPoint, PDF, images, RAW photos, SVG,
        DXF/DWG, STEP/STL, Figma/Sketch, IDML, audio and video. Read the file with craft_read first.

        Shortcuts (no command lookup needed):
          replace_json  Word documents: {"old text": "new text", ...}  (every occurrence)
          cells_json    spreadsheets: {"B4": "=SUM(B2:B3)", "A4": "Total", "Sheet2!C1": 5}
        Anything else: commands_json = JSON list of the app's engine commands, run in order:
          [{"command": "edit.replaceAll", "params": {"text": "2025", "with": "2026"}}]
          Find ids and params with craft_commands(app, search). Common ones: WordCraft text.insert {text, paragraphs?},
          select.text {text}, edit.replaceAll {text, with}; GridCraft cell.set {cell, input, sheet?}, range.setValues {range, values};
          DeckCraft slide.new {layout, title, body, at?}, slide.delete {index}, slide.notes {text, index?}, insert.chart {...};
          PdfCraft ops: rotate {pages, angle}, delete {pages}, move {from, to}, extract {pages}, insert-blank {after}, title {value}.

        :param file: file name (or part of it) or id; empty = the latest file.
        :param commands_json: JSON list of {"command", "params"} for the file's app.
        :param replace_json: JSON object of find -> replace pairs (documents).
        :param cells_json: JSON object of cell -> value or formula (spreadsheets).
        :param output_name: name for the edited copy (extension may change the format), default "<name> (edited)".
        :param open_in_desktop: also open the result in its app on the Craft desktop.
        :return: A download card for the edited file.
        """
        try:
            name, data, fid = await _load_file(file, __files__, __messages__, __user__)
            steps = json.loads(commands_json) if commands_json.strip() else []
            if isinstance(steps, dict):
                steps = [steps]
            for old, new in (json.loads(replace_json) if replace_json.strip() else {}).items():
                steps.append({"command": "edit.replaceAll", "params": {"text": str(old), "with": str(new)}})
            for cell, val in (json.loads(cells_json) if cells_json.strip() else {}).items():
                sheet, _, ref = str(cell).rpartition("!")
                p = {"cell": ref, "input": val if isinstance(val, str) else json.dumps(val)}
                if sheet:
                    p["sheet"] = sheet.strip("'")
                steps.append({"command": "cell.set", "params": p})
        except json.JSONDecodeError as e:
            return f"The edit JSON is invalid ({e}). Fix it and call craft_edit again."
        except Exception as e:
            return str(e)
        if not steps:
            return "Nothing to do: pass commands_json, replace_json or cells_json."
        app = CRAFT_EXT.get(name.rsplit(".", 1)[-1].lower(), "")
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Editing {name} with {CRAFT_APPS.get(app, (app or 'Craft',))[0]}…", "done": False}})
        try:
            async with aiohttp.ClientSession() as session:
                r = await _bridge_call(session, self._bridge(), "/edit", {"name": name, "b64": base64.b64encode(data).decode(),
                                                                          "commands": steps, "out": output_name or ""}, 300)
                out = base64.b64decode(r["b64"])
                fid2, url = await _store_file(__user__ or {}, r["name"], out, r.get("mime") or "application/octet-stream")
                prev = None
                try:
                    pr = await _bridge_call(session, self._bridge(), "/inspect", {"name": r["name"], "b64": r["b64"]}, 120)
                    prev = pr.get("preview")
                except Exception:
                    pass
                opened = False
                if open_in_desktop:
                    try:
                        await _bridge_call(session, self._bridge(), "/open", {"name": r["name"], "b64": r["b64"]}, 60)
                        opened = True
                    except Exception:
                        pass
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": "Edit failed", "done": True}})
            return f"Editing {name} failed: {e}. Check the command ids/params with craft_commands and try again."
        a = r.get("app", app)
        block = {"type": "file", "name": r["name"], "format": r["name"].rsplit(".", 1)[-1].lower(), "size": len(out), "url": url, "app": a,
                 "app_name": CRAFT_APPS.get(a, (a,))[0], "maker": CRAFT_APPS.get(a, (a,))[0], "opened": opened, "mode": "edit",
                 "preview": ("data:image/jpeg;base64," + prev) if prev else "", "note": f"Edited copy of {name} · {len(steps)} change(s)"}
        resp = await self._file_card(block, __event_call__, __request__)
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"{r['name']} is ready", "done": True}})
        return resp, (f"Edited copy saved as “{r['name']}” (id {fid2}); the original is unchanged. A download card is shown. "
                      "To make more changes, call craft_edit on the new file name. Reply with one short sentence.")

    async def craft_convert(self, file: str = "", format: str = "pdf", __user__: dict = None, __files__: list = None,
                            __messages__: list = None, __event_emitter__=None, __event_call__=None, __request__=None) -> tuple:
        """
        Convert a file the user uploaded (or made earlier) to another format with its ArtCraft app:
        docx<->pdf/odt/rtf/md/html/txt, pptx->pdf/md, xlsx<->csv/pdf/html, pdf->docx/txt/png, images (psd, png, jpg, webp, tif…),
        RAW photo->jpg/png, svg/ai/eps<->pdf/png/svg, dxf<->dwg/svg/pdf/png, step/stl conversions, audio (wav/flac/aiff), video export.

        :param file: file name (or part of it) or id; empty = the latest file.
        :param format: target extension, e.g. pdf, docx, png, csv, flac.
        :return: A download card for the converted file.
        """
        try:
            name, data, _ = await _load_file(file, __files__, __messages__, __user__)
            async with aiohttp.ClientSession() as session:
                r = await _bridge_call(session, self._bridge(), "/convert", {"name": name, "b64": base64.b64encode(data).decode(), "format": format}, 300)
            out = base64.b64decode(r["b64"])
            fid2, url = await _store_file(__user__ or {}, r["name"], out, r.get("mime") or "application/octet-stream")
        except Exception as e:
            return f"Converting failed: {e}"
        a = r.get("app", "")
        block = {"type": "file", "name": r["name"], "format": r["name"].rsplit(".", 1)[-1].lower(), "size": len(out), "url": url, "app": a,
                 "app_name": CRAFT_APPS.get(a, (a,))[0], "maker": CRAFT_APPS.get(a, (a,))[0], "note": f"Converted from {name}"}
        return await self._file_card(block, __event_call__, __request__), f"Converted {name} to {r['name']}; a download card is shown. Reply with one short sentence."

    async def craft_commands(self, app: str, search: str = "") -> str:
        """
        Look up the engine commands (ids and parameters) an ArtCraft app accepts, for craft_edit.
        Apps: wordcraft, gridcraft, deckcraft, pdfcraft, photocraft, lightcraft, vectorcraft, designcraft, figcraft, filmcraft,
        effectcraft, soundcraft, cadcraft, solidcraft. Always pass a search (e.g. "replace", "cell", "slide", "resize", "export").

        :param app: the app id.
        :param search: words that must appear in the command (id, label or parameters).
        :return: Matching commands with their parameters.
        """
        try:
            async with aiohttp.ClientSession() as session:
                r = await _bridge_call(session, self._bridge(), "/commands", {"app": app.lower().strip(), "search": search}, 90)
            return f"{app} commands matching '{search}':\n{r.get('commands', '')}"
        except Exception as e:
            return f"Could not list commands: {e}"
