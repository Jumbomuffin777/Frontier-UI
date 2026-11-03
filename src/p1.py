"""
title: Frontier UI
author: Zability (Claude Opus 5.5); inspired by ChatGPT Intelligent UI and thesysdev/open-intelligent-ui (MIT)
version: 1.3.2
description: ChatGPT-style generative UI: photo galleries, street maps with multi-day routes (self-hosted planet tiles), filterable place cards, itineraries, budgets, calculators, live weather and quotes, link previews, Gmail drafts, calendar export, real Word/Excel/PowerPoint/PDF files, and reading + editing your uploaded files with all 16 ArtCraft apps.
required_open_webui_version: 0.6.0
"""
import asyncio
import json
import math
import re
import secrets
from urllib.parse import urlparse

import aiohttp
from typing import Literal

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
    # short timeout: an unreachable SearXNG must leave time for the keyless fallbacks inside the 8 s photo budget
    data = await _get_json(session, base.rstrip("/") + "/search", {"q": q, "categories": "images", "format": "json", "safesearch": "1"}, timeout=3)
    out = []
    for r in (data.get("results") or [])[:12]:
        src = r.get("img_src") or ""
        if not src.startswith("https://") or _SKIP_IMG.search(src):
            continue
        out.append({"src": src, "page": r.get("url", ""), "title": r.get("title", "")})
    return out


async def _commons_images(session, q):
    """Wikimedia Commons file search (keyless, hotlink-friendly thumbnails, licence + author for attribution)."""
    data = await _get_json(session, "https://commons.wikimedia.org/w/api.php", {
        "action": "query", "format": "json", "formatversion": "2", "generator": "search", "gsrsearch": f"{q} filetype:bitmap",
        "gsrnamespace": "6", "gsrlimit": "8", "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": "960",
        "iiextmetadatafilter": "Artist|LicenseShortName"})
    wanted, out = _words(q), []
    for p in sorted((data.get("query") or {}).get("pages") or [], key=lambda p: p.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        src = ii.get("thumburl") or ii.get("url") or ""
        title = re.sub(r"^File:|\.\w{3,4}$", "", p.get("title", ""))
        overlap = len(_words(title) & wanted) / max(1, len(wanted))
        if src.startswith("https://") and not _SKIP_IMG.search(src) and (not wanted or overlap >= 0.5):
            md = ii.get("extmetadata") or {}
            artist = re.sub(r"<[^>]+>", "", (md.get("Artist") or {}).get("value", "")).strip()[:80]
            lic = (md.get("LicenseShortName") or {}).get("value", "")
            out.append({"src": src, "page": ii.get("descriptionurl", ""), "title": title,
                        "credit": " · ".join(x for x in (artist, lic, "Wikimedia Commons") if x)})
    return out


async def _openverse_images(session, q):
    """Openverse (WordPress.org) CC-licensed images; anonymous access is rate limited, so it is a late fallback."""
    data = await _get_json(session, "https://api.openverse.org/v1/images/", {"q": q, "page_size": "8", "mature": "false"})
    out, wanted = [], _words(q)
    for r in (data.get("results") or [])[:8]:
        src = r.get("thumbnail") or r.get("url") or ""
        overlap = len(_words(f"{r.get('title', '')} {' '.join(t.get('name', '') for t in r.get('tags') or [] if isinstance(t, dict))}") & wanted) / max(1, len(wanted))
        if src.startswith("https://") and not _SKIP_IMG.search(src) and (len(wanted) < 2 or overlap >= 0.34):
            out.append({"src": src, "page": r.get("foreign_landing_url", ""), "title": r.get("title", ""),
                        "credit": " · ".join(x for x in (r.get("creator"), (r.get("license") or "").upper() and f"CC {(r.get('license') or '').upper()}", "Openverse") if x)})
    return out


async def _keyed_json(session, url, params, headers, timeout=6):
    """GET for providers that need a key. The key travels only in server-side headers/params, never to the browser;
    errors are reported without the URL so a key in the query string can't leak into logs or tool output."""
    try:
        async with session.get(url, params=params, headers={**UA, **headers}, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}")
            return await r.json(content_type=None)
    except asyncio.TimeoutError:
        raise RuntimeError("timeout")
    except aiohttp.ClientError as e:
        raise RuntimeError(type(e).__name__)


async def _brave_images(session, q, key):
    data = await _keyed_json(session, "https://api.search.brave.com/res/v1/images/search", {"q": q, "count": "10", "safesearch": "strict"},
                             {"X-Subscription-Token": key, "Accept": "application/json"})
    return [{"src": (r.get("thumbnail") or {}).get("src") or (r.get("properties") or {}).get("url", ""), "page": r.get("url", ""),
             "title": r.get("title", ""), "credit": r.get("source", "")} for r in (data.get("results") or [])[:10]
            if ((r.get("thumbnail") or {}).get("src") or "").startswith("https://")]


async def _google_images(session, q, key, cx):
    data = await _keyed_json(session, "https://www.googleapis.com/customsearch/v1",
                             {"key": key, "cx": cx, "q": q, "searchType": "image", "num": "10", "safe": "active"}, {})
    return [{"src": it.get("link", ""), "page": (it.get("image") or {}).get("contextLink", ""), "title": it.get("title", ""),
             "credit": it.get("displayLink", "")} for it in (data.get("items") or []) if str(it.get("link", "")).startswith("https://")]


async def _pexels_images(session, q, key):
    data = await _keyed_json(session, "https://api.pexels.com/v1/search", {"query": q, "per_page": "8"}, {"Authorization": key})
    return [{"src": (p.get("src") or {}).get("large", ""), "page": p.get("url", ""), "title": p.get("alt", "") or q,
             "credit": f"Photo by {p.get('photographer', '')} on Pexels"} for p in (data.get("photos") or [])]


async def _unsplash_images(session, q, key):
    data = await _keyed_json(session, "https://api.unsplash.com/search/photos", {"query": q, "per_page": "8", "content_filter": "high"},
                             {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"})
    return [{"src": (p.get("urls") or {}).get("regular", ""), "page": ((p.get("links") or {}).get("html", "") + "?utm_source=frontier_ui&utm_medium=referral"),
             "title": p.get("alt_description") or q, "credit": f"Photo by {(p.get('user') or {}).get('name', '')} on Unsplash"}
            for p in (data.get("results") or [])]


_DOWN: dict = {}  # provider -> time it failed; skipped for a few minutes so a missing SearXNG never slows every card


def _provider_up(name):
    return time.time() - _DOWN.get(name, 0) > 300


FALLBACK_DEADLINE = 6.5  # seconds into a photo lookup after which no fallback starts (run_img gives up at 8 s)


async def _images_for(session, searx, q, wiki=True, cfg=None, fallback=None, _depth=0):
    """Photo candidates from a fallback chain that works with no services and no keys:
    SearXNG (if reachable) + optional keyed providers, then Wikipedia + Wikimedia Commons, then Openverse.
    `cfg` = {"provider": "auto"|name, "brave_key", "google_key", "google_cx", "pexels_key", "unsplash_key"}.
    `fallback` = a second string (usually the caption) to try, shortened, when the query finds fewer than 3 photos."""
    t0 = time.monotonic()
    cfg = cfg or {}
    q = re.sub(r"\s+", " ", str(q or "")).strip()[:160]
    if len(q) < 2:
        return []
    want = cfg.get("provider") or "auto"
    ck = (q, want, bool(searx), bool(wiki), str(fallback or "")[:80] if _depth == 0 else "")
    if ck in _IMG_CACHE:
        return _IMG_CACHE[ck]
    p = {}
    if searx:
        p["searxng"] = lambda: _searx_images(session, searx, q)
    if cfg.get("brave_key"):
        p["brave"] = lambda: _brave_images(session, q, cfg["brave_key"])
    if cfg.get("google_key") and cfg.get("google_cx"):
        p["google"] = lambda: _google_images(session, q, cfg["google_key"], cfg["google_cx"])
    p["wikipedia"] = lambda: _wiki_images(session, q)
    p["commons"] = lambda: _commons_images(session, q)
    p["openverse"] = lambda: _openverse_images(session, q)
    if cfg.get("pexels_key"):
        p["pexels"] = lambda: _pexels_images(session, q, cfg["pexels_key"])
    if cfg.get("unsplash_key"):
        p["unsplash"] = lambda: _unsplash_images(session, q, cfg["unsplash_key"])
    if want != "auto" and want in p:
        tiers = [[want], [n for n in ("wikipedia", "commons") if n != want], ["openverse"]]
    else:
        web = [n for n in ("searxng", "brave", "google") if n in p]
        # landmarks/topics (galleries, heroes) get Wikipedia first; named businesses lean on web search
        tiers = [web + (["wikipedia", "commons"] if wiki or not web else []), ["wikipedia", "commons"] if web and not wiki else [],
                 ["openverse"] + [n for n in ("pexels", "unsplash") if n in p]]
    seen, out = set(), []

    async def run_tiers(tier_list):
        for tier in tier_list:
            tier = [n for n in dict.fromkeys(tier) if n in p and _provider_up(n) and n not in seen]
            if not tier or len(out) >= 3:
                continue
            res = await asyncio.gather(*(p[n]() for n in tier), return_exceptions=True)
            for n, group in zip(tier, res):
                seen.add(n)
                if isinstance(group, Exception):
                    if n in ("searxng", "brave", "google", "pexels", "unsplash"):
                        _DOWN[n] = time.time()
                    continue
                for it in group:
                    if it.get("src") and it["src"] not in {o["src"] for o in out}:
                        it.setdefault("provider", n)
                        out.append(it)

    # fast sources first (web search, Wikipedia, Commons); the slow tail (Openverse, stock APIs) runs below, alongside
    # the shorter fallback searches, so neither waits for the other inside the 8 s photo budget
    await run_tiers(tiers[:2])
    slow = None
    if len(out) < 3 and not _depth and any(tiers[2:]):
        slow = asyncio.ensure_future(run_tiers(tiers[2:]))
    budget = FALLBACK_DEADLINE - (time.monotonic() - t0)
    if len(out) < 3 and _depth == 0 and budget > 0.5:
        # a long or adjective-heavy query ("brown tabby Maine Coon cat") matches little or nothing: top up from
        # shorter heads, since the title-match gate scores overlap against the whole query (PR #1, ondrejch).
        # Caption/query head before a dash: always. First/last two words: only for gallery and hero photos (wiki=True);
        # for a place card "Ichiran Ramen Shibuya Tokyo" -> "Shibuya Tokyo" would show the district, not the restaurant.
        words = q.split()
        heads = []
        for s in (fallback, q):
            s = re.sub(r"\s+", " ", str(s or "")).strip()
            heads.append(re.split(r"\s+[—–·|]\s+|\s+-\s+|[,(]", s)[0].strip() if s else "")
        # most specific first; broad ones (a single word like "Persian", or leading adjectives like "silver classic")
        # only fill gaps, because "Persian" alone finds the Persian Gulf as readily as the cat
        strong = ([" ".join(words[-2:])] if wiki and len(words) > 3 else []) + [h for h in heads if len(h.split()) >= 2]
        weak = [h for h in heads if len(h.split()) == 1] + ([" ".join(words[:2])] if wiki and len(words) > 3 else [])
        alts = [a for a in dict.fromkeys(strong + weak) if a and a != q and len(a) >= 2][:4]
        weak = set(weak) - set(strong)
        if alts:
            # in parallel and inside what is left of the photo budget: a slow fallback must never cost the photos the
            # original query already found (run_img's 8 s timeout would otherwise discard everything)
            tasks = [asyncio.ensure_future(_images_for(session, searx, a, wiki, cfg, _depth=1)) for a in alts]
            done, pending = await asyncio.wait(tasks, timeout=budget)
            for t in pending:
                t.cancel()
            if pending:  # let the cancellations finish so no request is left dangling
                await asyncio.gather(*pending, return_exceptions=True)
            for a, t in zip(alts, tasks):  # in priority order; broad alternatives only while photos are still missing
                if t not in done or t.cancelled() or t.exception() or (a in weak and len(out) >= 3):
                    continue
                for it in t.result() or []:
                    if it.get("src") and it["src"] not in {o["src"] for o in out}:
                        out.append(dict(it, fallback=a))
    if slow is not None:  # the slow tier: only worth waiting for while photos are still missing, and never past the budget
        if len(out) < 3:
            await asyncio.wait([slow], timeout=max(0.1, FALLBACK_DEADLINE - (time.monotonic() - t0)))
        if not slow.done():
            slow.cancel()
            await asyncio.gather(slow, return_exceptions=True)
    # photos first: transparent PNG cut-outs look empty as tiles, keep them as late fallbacks
    out = sorted(out, key=lambda it: 1 if re.search(r"\.png(\?|$)", it["src"], re.I) else 0)[:8]
    if out:
        _cache_put(_IMG_CACHE, ck, out)
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


ROUTE_MODES = {"walk": "walk", "walking": "walk", "foot": "walk", "hike": "walk", "hiking": "walk",
               "bike": "bike", "bicycle": "bike", "cycling": "bike", "cycle": "bike",
               "drive": "drive", "driving": "drive", "car": "drive", "motorcycle": "drive", "motorbike": "drive",
               "moto": "drive", "road trip": "drive", "roadtrip": "drive", "auto": "auto", "": "auto"}


def _route_mode(m):
    return ROUTE_MODES.get(str(m or "auto").strip().lower(), "auto")


class RouteError(RuntimeError):
    pass


async def _route(session, pts, mode="auto"):
    """Street geometry in visiting order from keyless public OSRM servers. City-scale stops default to walking
    (FOSSGIS foot router), longer trips to driving (OSRM demo, FOSSGIS car as backup); bike uses FOSSGIS bike.
    Raises RouteError with a reason the card can show."""
    spread = max(_km(pts[0], q) for q in pts)
    mode = _route_mode(mode)
    if mode == "auto":
        mode = "walk" if spread < 12 else "drive"
    key = (mode, tuple((round(a, 5), round(b, 5)) for a, b in pts))
    if key in _ROUTE_CACHE:
        return _ROUTE_CACHE[key]
    coords = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in pts)
    fossgis = "https://routing.openstreetmap.de/routed-{}/route/v1/driving/" + coords
    urls = {"walk": [(fossgis.format("foot"), "walk"), (fossgis.format("car"), "drive")],
            "bike": [(fossgis.format("bike"), "bike"), (fossgis.format("car"), "drive")],
            "drive": [(f"https://router.project-osrm.org/route/v1/driving/{coords}", "drive"), (fossgis.format("car"), "drive")]}[mode]
    last = "routing service unavailable"
    for u, used in urls:
        try:
            data = await _get_json(session, u, {"overview": "full", "geometries": "geojson", "steps": "false"}, timeout=8)
        except Exception as e:
            last = f"routing service unavailable ({str(e).split()[-1][:20]})"
            continue
        if data.get("code") == "Ok" and data.get("routes"):
            r0 = data["routes"][0]
            out = {"line": [[c[1], c[0]] for c in r0["geometry"]["coordinates"]], "km": r0.get("distance", 0) / 1000.0,
                   "min": r0.get("duration", 0) / 60.0, "mode": used}
            _cache_put(_ROUTE_CACHE, key, out, 200)
            return out
        last = {"NoRoute": "no road connects these stops", "NoSegment": "a stop is too far from any road",
                "TooBig": "too many stops for the router"}.get(data.get("code"), f"router said {data.get('code')}")
        if data.get("code") in ("NoRoute", "NoSegment"):
            break
    raise RouteError(last)


class SpecError(ValueError):
    """A spec the tool could not read; the message tells the model exactly what to fix."""


def _close_truncated(s):
    """Close strings/brackets left open by output that was cut off mid-way."""
    stack, instr, esc = [], False, False
    for ch in s:
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
            continue
        if ch == '"':
            instr = True
        elif ch in "[{":
            stack.append("]" if ch == "[" else "}")
        elif ch in "]}" and stack:
            stack.pop()
    s = s.rstrip()
    if instr:
        s += '"'
    s = re.sub(r",\s*$", "", s)
    s = re.sub(r':\s*$', ': null', s)
    return s + "".join(reversed(stack))


def _loads_lenient(spec, _depth=0):
    """Parse a spec that small models often emit slightly wrong. Bounded repairs only (each is a known, common failure);
    anything else raises SpecError with the position and a snippet so the model can fix its JSON."""
    if isinstance(spec, (dict, list)):
        return spec
    s = str(spec or "").strip().lstrip("﻿")
    if not s:
        raise SpecError("spec is empty. Pass one JSON object like {\"title\": \"…\", \"blocks\": [{\"type\": \"text\", \"md\": \"…\"}]}.")
    s = re.sub(r"^```[a-zA-Z]*\s*|\s*```\s*$", "", s)  # code fences
    attempts = [s]
    a, b = s.find("{"), s.rfind("}")
    if a > 0 or (b != -1 and b < len(s) - 1):  # prose around the object
        attempts.append(s[a:b + 1] if a != -1 and b > a else s[a:] if a != -1 else s)
    first_err = None
    for t in list(attempts):
        t2 = (t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'"))
        t3 = re.sub(r",\s*([}\]])", r"\1", t2)  # trailing commas
        for cand in dict.fromkeys([t, t2, t3, _close_truncated(t3)]):
            try:
                v = json.loads(cand, strict=False)  # strict=False: raw newlines/tabs inside strings
            except json.JSONDecodeError as e:
                first_err = first_err or (e, cand)
                continue
            if isinstance(v, str) and _depth < 2:  # double-encoded: a JSON string that contains the JSON
                return _loads_lenient(v, _depth + 1)
            return v
        try:  # Python-style literals: single quotes, True/False/None
            import ast
            v = ast.literal_eval(t3)
            if isinstance(v, (dict, list)):
                return v
        except Exception:
            pass
    e, cand = first_err if first_err else (None, s)
    if e is None:
        raise SpecError("spec is not JSON.")
    lo = max(0, e.pos - 60)
    raise SpecError(f"spec JSON is invalid at character {e.pos} ({e.msg}): …{cand[lo:e.pos + 40]}… "
                    "Check quotes and commas there, keep it to ONE object, and call the tool again.")


BLOCK_ALIASES = {"gallery": "images", "photos": "images", "image": "images", "itinerary": "timeline", "schedule": "timeline",
                 "cards": "places", "place": "places", "restaurants": "places", "markdown": "text", "paragraph": "text",
                 "note": "callout", "tip": "callout", "warning": "callout", "kpi": "stats", "metrics": "stats",
                 "graph": "chart", "comparison": "compare", "howto": "steps", "route": "map", "maps": "map",
                 "forecast": "weather", "stocks": "stock", "quote_card": "quote", "link": "links", "previews": "links"}
KNOWN_BLOCKS = {"text", "images", "map", "places", "timeline", "table", "stats", "chart", "callout", "compare", "steps", "hero",
                "quote", "budget", "calculator", "weather", "stock", "links", "email", "status", "apps"}


def _unescape_text(v):
    """Literal "\\n" sequences (double-escaped by the model) become real line breaks in prose."""
    if isinstance(v, str) and "\\n" in v and "\n" not in v:
        return v.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "  ")
    return v


def _normalize_spec(data):
    """Accept the shapes models actually send, fix harmless slips, and list what was changed or dropped."""
    notes = []
    if isinstance(data, dict) and isinstance(data.get("spec"), (dict, str)) and "blocks" not in data:
        data = _loads_lenient(data["spec"])  # {"spec": {...}} wrapper
    if isinstance(data, list):
        data = {"blocks": data}
    if not isinstance(data, dict):
        raise SpecError("spec must be a JSON object with a \"blocks\" array.")
    blocks = data.get("blocks")
    if blocks is None:
        for k in ("components", "sections", "content", "items"):
            if isinstance(data.get(k), list):
                blocks = data.pop(k)
                notes.append(f"used '{k}' as blocks")
                break
    if isinstance(blocks, dict):
        blocks = [blocks]
    if not isinstance(blocks, list) or not blocks:
        if data.get("md") or data.get("text"):
            blocks = [{"type": "text", "md": data.get("md") or data.get("text")}]
        else:
            raise SpecError("spec has no \"blocks\" array. Example: {\"title\": \"Kyoto\", \"blocks\": [{\"type\": \"text\", \"md\": \"…\"}, "
                            "{\"type\": \"map\", \"places\": [{\"name\": \"Kiyomizu-dera\", \"lat\": 34.99, \"lng\": 135.78}]}]}")
    out = []
    for i, b in enumerate(blocks):
        if isinstance(b, str):
            b = {"type": "text", "md": b}
        if not isinstance(b, dict):
            notes.append(f"block {i} dropped (not an object)")
            continue
        t = str(b.get("type") or b.get("kind") or "").strip().lower()
        if t in BLOCK_ALIASES:
            b["type"] = BLOCK_ALIASES[t]
        elif t not in KNOWN_BLOCKS:
            if any(k in b for k in ("md", "text", "content")):
                b = {"type": "text", "title": b.get("title"), "md": b.get("md") or b.get("text") or b.get("content")}
                notes.append(f"block {i} type '{t or '?'}' shown as text")
            else:
                notes.append(f"block {i} dropped (unknown type '{t or '?'}')")
                continue
        else:
            b["type"] = t
        for k in ("md", "text", "detail", "description", "body", "subtitle", "note"):
            if k in b:
                b[k] = _unescape_text(b[k])
        L = lambda x: x if isinstance(x, list) else []
        nested = L(b.get("items")) + L(b.get("places"))
        for d in L(b.get("days")):
            if isinstance(d, dict):
                nested += L(d.get("places"))
        for it in nested:
            if isinstance(it, dict):
                for k in ("md", "text", "detail", "description", "note"):
                    if k in it:
                        it[k] = _unescape_text(it[k])
        out.append(b)
    if not out:
        raise SpecError("none of the blocks could be used: " + "; ".join(notes))
    data["blocks"] = out
    for k in ("title", "subtitle"):
        data[k] = _unescape_text(data.get(k)) if data.get(k) else data.get(k)
    return data, notes
