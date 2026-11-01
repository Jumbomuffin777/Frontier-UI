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
