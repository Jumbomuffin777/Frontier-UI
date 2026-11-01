

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
