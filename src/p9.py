

class Tools:
    """Frontier UI: rich, ChatGPT-style visual answers (photos, maps, places, itineraries, charts, live data) plus real
    Word/Excel/PowerPoint/PDF files made with the Craft apps, Gmail drafts and Open WebUI notes."""

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

    async def _card(self, spec, __event_call__):
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
        resp = await self._card(data, __event_call__)
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Showing “{title}”", "done": True}})
        kinds = [b.get("type") for b in data.get("blocks", []) if isinstance(b, dict)]
        return resp, (f"Frontier UI card “{title}” (card id: {card}) is rendered and visible to the user (blocks: {', '.join(map(str, kinds))}). "
                      "Reply with one or two short sentences that add context; do not repeat the card or show JSON. "
                      f"If the user later asks to export or save this card, call craft_file or save_note with card=\"{card}\".")

    # ---------------- 2. real Office files via the Craft apps ----------------
    async def craft_file(self, format: str, card: str = "", title: str = "", markdown: str = "", rows_json: str = "", slides_json: str = "",
                         open_in_desktop: bool = False, __user__: dict = None, __event_emitter__=None, __event_call__=None) -> tuple:
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
        resp = await self._card({"blocks": [block], "_ui": ui}, __event_call__)
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"{res['name']} is ready", "done": True}})
        return resp, (f"The file {res['name']} ({len(data) // 1024 + 1} KB, made with {block['app_name']}) was created and a download card is shown"
                      + (" ; it is also open in the Craft desktop" if block["opened"] else "") + ". Reply with one short sentence; do not paste links.")

    # ---------------- 3. open anything in a Craft app ----------------
    async def craft_open(self, url: str, app: str = "", __event_emitter__=None, __event_call__=None) -> tuple:
        """
        Open a public image, PDF, SVG, audio or video URL in a Craft app on the streamed Craft desktop
        (PhotoCraft/LightCraft for photos, PdfCraft for PDFs, VectorCraft for SVG, FilmCraft for video, SoundCraft for audio).

        :param url: public http(s) URL of the file.
        :param app: optional app id: photocraft, lightcraft, pdfcraft, vectorcraft, filmcraft, soundcraft, wordcraft, gridcraft, deckcraft, cadcraft.
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
        resp = await self._card({"blocks": [block], "_ui": ui}, __event_call__)
        return resp, f"Opened in {block['app_name']} on the Craft desktop (saved to ~/Inbox). Reply with one short sentence."

    # ---------------- 4. Open WebUI notes ----------------
    async def save_note(self, title: str = "", markdown: str = "", card: str = "", __user__: dict = None, __event_call__=None) -> tuple:
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
        resp = await self._card({"blocks": [{"type": "note", "name": name, "url": f"/notes/{nid}" if nid else ""}], "_ui": ui}, __event_call__)
        return resp, f"Saved to Notes as “{name}”. Reply with one short sentence."
