

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
