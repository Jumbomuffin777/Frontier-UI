

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


