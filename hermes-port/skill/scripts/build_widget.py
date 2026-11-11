#!/usr/bin/env python3
"""Hermes generative-UI widget builder v2 — port of Frontier-UI blocks.
Usage: python3 build_widget.py spec.json out.html

Spec v2: {title, units(metric|imperial), followups[], blocks:[
  {type:text,md}|{type:hero,h,sub}|{type:stats,items:[{l,v,d}]}|{type:chart,kind,labels,values,unit}
  {type:table,headers,rows}|{type:compare,columns:[{h,items}]}|{type:steps,items:[md]}
  {type:callout,icon,title,md}|{type:quote,md,cite}|{type:status,items:[{dot,label,note}]}
  {type:links,items:[{url,title?,desc?}]}|{type:weather,place?|lat,lon}|{type:stock,symbols:[{sym,name}]}
  {type:budget,items:[{label,cost}],cap?,per_person?}|{type:calculator,title,expr,unit?,money?,vars:{k:{label,min,max,def}}}
  {type:email,subject,body?}|{type:ics}|{type:sources,items:[{title,url}]}|{type:images,items:[{query|name,page?,hint?}]}
  {type:map,hint,mode?,stops:[{name,page?,hint?,rating?,price?,tags?,area?}],routes:[{label,mode?}]?,timeline via separate block}
  {type:timeline,items:[{time,title,place?,day?,md?}]}
]}
Sandbox rule (upstream #144361): NO anchors/window.open/blob/clipboard survive; every
action is a data-hermes-send prompt the agent later executes. Never use f-strings for JS.
"""
import json, sys, os, re, math, html as H, subprocess, urllib.request, urllib.parse, urllib.error, time

UA = {"User-Agent": "Mozilla/5.0 (compatible; HermesGenUI/2.0 personal assistant)"}
SEARXNG = os.environ.get("HERMES_SEARXNG", "http://192.168.100.212:4000")
PALETTE = ["#e5484d", "#3e63dd", "#30a46c", "#f2a33c", "#a855f7", "#0ea5e9"]
notes_global = []

def get(url, timeout=20, retry=True):
    req = urllib.request.Request(url, headers=UA)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
    except urllib.error.HTTPError as he:
        if retry and he.code in (403, 429):
            time.sleep(2.0)
            return get(url, timeout, retry=False)
        raise

TW_HINT = re.compile(r"(台灣|臺灣|台北|新北|桃園|台中|高雄|台南|基隆|新竹|嘉義|屏東|宜蘭|花蓮|台東|苗栗|彰化|南投|雲林|金門|澎湖)")
NEAR = []  # geocoded points of this build, used for sanity
SUFFIX_TRIMS = ("老街", "舊街", "景區", "風景區", "國家公園", "森林公園", "公園", "車站", "街")

def wiki_coords(page):
    for host in ("zh", "en"):
        try:
            s = get(f"https://{host}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page)}")
            c = s.get("coordinates")
            if c and c.get("lat") and c.get("lon"): return float(c["lat"]), float(c["lon"])
        except Exception: pass
    return None

def geocode_candidates(name, hint, page=None):
    res = []
    def add(p):
        if p and not any(abs(p[0]-q[0]) < 0.01 and abs(p[1]-q[1]) < 0.01 for q in res): res.append(p)
    for pg in [x for x in (page, name) if x]:
        add(wiki_coords(pg))
    cc = "&countrycodes=tw" if hint and TW_HINT.search(hint) else ""
    q2 = [name] + ([name + " " + hint] if hint else [])
    for suf in SUFFIX_TRIMS:
        if name.endswith(suf) and len(name) > len(suf) + 1: q2.append(name[: -len(suf)])
    base = name
    while len(base) > 2 and len(q2) < 7:
        base = base[:-1]; q2.append(base)  # CJK tail-trim: progressively strip trailing characters
    for q in q2:
        if not q.strip(): continue
        try:
            r = get("https://nominatim.openstreetmap.org/search?format=json&limit=1" + cc + "&q=" + urllib.parse.quote(q.strip()))
            if r: add((float(r[0]["lat"]), float(r[0]["lon"])))
        except Exception: pass
    try:  # Wikidata search + coordinates: minor sites (ruins/shrines/tunnels) often lack a wiki article
        s = get("https://www.wikidata.org/w/api.php?action=query&format=json&origin=*&list=search"
                "&srsearch=" + urllib.parse.quote((name + " " + (hint or "")).strip()) + "&srnamespace=0&srlimit=3")
        titles = [h["title"] for h in (s.get("query") or {}).get("search", []) if h.get("ns") == 0]
        if titles:
            q = get("https://www.wikidata.org/w/api.php?action=query&format=json&origin=*&prop=coordinates"
                    "&titles=" + urllib.parse.quote("|".join(titles[:3])))
            for pg in (q.get("query") or {}).get("pages", {}).values():
                for c in pg.get("coordinates", []):
                    try: add((float(c["lat"]), float(c["lon"])))
                    except (KeyError, ValueError): pass
                    break
    except Exception: pass
    try:  # Photon as last resort
        u = "https://photon.komoot.io/api/?format=json&lang=zh&limit=1&q=" + urllib.parse.quote(name)
        if NEAR: u += f"&lat={NEAR[-1][0]}&lon={NEAR[-1][1]}"
        hits = get(u).get("features", [])
        if hits:
            lon, lat = hits[0]["geometry"]["coordinates"]
            add((lat, lon))
    except Exception: pass
    return res

def _d(p, q): return abs(p[0]-q[0]) + abs(p[1]-q[1])  # ~111km per unit; 3.0 ≈ 330km

def geocode(name, hint, page=None):
    c = geocode_candidates(name, hint, page)
    if not c: raise SystemExit(f"geocode failed: {name} — add 'page' (wikipedia article) or a more precise hint")
    pick = c[0]
    if NEAR:
        best = min(c, key=lambda p: _d(p, NEAR[-1]))
        if _d(best, NEAR[-1]) <= 3.0 and _d(pick, NEAR[-1]) > 3.0:
            notes_global.append(f"geocode re-ranked {name} toward itinerary cluster")
            pick = best
    NEAR.append(pick)
    return pick

def osrm(points, mode):
    host, prof = {"foot": ("routed-foot", "foot"), "bike": ("routed-bike", "bike"), "car": ("routed-car", "driving")}[mode]
    pts = ";".join(f"{lon},{lat}" for lat, lon in points)
    return get(f"https://routing.openstreetmap.de/{host}/route/v1/{prof}/{pts}?overview=full&geometries=geojson")["routes"][0]

def photo(name, page, searxng):
    if searxng:
        try:
            r = get(f"{searxng}/search?format=json&categories=images&q=" + urllib.parse.quote(name), timeout=8)
            for it in r.get("results", [])[:6]:
                u = it.get("img_src") or it.get("thumbnail") or ""
                if u.startswith("//"): u = "https:" + u
                # filter hotlink-blocked image hosts (pinimg/pixnet 403); allow only directly-linkable CDNs
                if u.startswith("http") and any(h in u for h in ("wikimedia.org", "wikipedia.org", "staticflickr.com", "openverse.org", "unsplash.com")):
                    return u, it.get("url", ""), "searxng"
        except Exception: pass
    for host in ("zh", "en"):
        try:
            s = get(f"https://{host}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page or name)}")
            u = (s.get("originalimage") or {}).get("source") or (s.get("thumbnail") or {}).get("source")
            if u: return u, (s.get("content_urls") or {}).get("desktop", {}).get("page", ""), "wikipedia"
        except Exception: pass
    try:
        s = get("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
                f"&gsrsearch={urllib.parse.quote(name)}&gsrlimit=3&prop=imageinfo&iiprop=url&iiurlwidth=640&gsrnamespace=6")
        pages = sorted((s.get("query") or {}).get("pages", {}).values(), key=lambda x: x.get("index", 9))
        if pages and pages[0].get("imageinfo"):
            ii = pages[0]["imageinfo"][0]
            return ii.get("thumburl") or ii.get("url"), "", "commons"
    except Exception: pass
    return None, "", "none"

def md(s):
    s = H.escape(s or "")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    s = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r'\1 <span class="r">(\1)</span>', s)  # links dead in sandbox: strip href
    out = "".join(f"<p>{p}</p>" for p in s.split("\n\n") if p.strip())
    return out or "<p></p>"

def svg_chart(kind, labels, values, unit=""):
    n = len(values); mx = max(values) or 1; w, hgt, pad = 720, 150, 24
    body = ""
    if kind == "bar":
        bw = (w - pad * 2) / n * 0.7
        for i, v in enumerate(values):
            x = pad + (w - pad * 2) * i / n
            hh = (hgt - 40) * v / mx
            body += f'<rect x="{x:.1f}" y="{hgt-24-hh:.1f}" width="{bw:.1f}" height="{hh:.1f}" rx="3" fill="var(--accent)"/>'
            body += f'<text x="{x+bw/2:.1f}" y="{hgt-8}" text-anchor="middle" font-size="10" fill="var(--muted-foreground)">{H.escape(str(labels[i]))}</text>'
            body += f'<text x="{x+bw/2:.1f}" y="{hgt-30-hh:.1f}" text-anchor="middle" font-size="10" fill="var(--foreground)">{H.escape(str(v))}</text>'
    else:
        pts = " ".join(f"{pad+(w-pad*2)*i/(n-1):.1f},{hgt-24-(hgt-48)*v/mx:.1f}" for i, v in enumerate(values))
        body = f'<polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>'
        for i, v in enumerate(values):
            x = pad + (w - pad * 2) * i / (n - 1)
            body += f'<text x="{x:.1f}" y="{hgt-8}" text-anchor="middle" font-size="10" fill="var(--muted-foreground)">{H.escape(str(labels[i]))}</text>'
    t = f' <tspan fill="var(--muted-foreground)" font-size="10">{H.escape(unit)}</tspan>' if unit else ""
    return f'<svg viewBox="0 0 {w} {hgt}" style="width:100%">{body}</svg>'

def spark(points, w=100, h=40):
    vals = [v for v in points if v is not None]
    if len(vals) < 2: return ""
    lo, hi = min(vals), max(vals); rng = (hi - lo) or 1
    pts = " ".join(f"{w*i/(len(points)-1):.1f},{h-(h-4)*(v-lo)/rng+2:.1f}" for i, v in enumerate(points) if v is not None)
    return f'<polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="1.6"/>'

def favicon(url):
    d = urllib.parse.urlparse(url).netloc
    return f'<img src="https://icons.duckduckgo.com/ip3/{d}.ico" alt="">', d

def page_title(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        raw = urllib.request.urlopen(req, timeout=12).read(60000).decode("utf-8", "ignore")
        m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
        if m: return re.sub(r"\s+", " ", m.group(1)).strip()[:90]
    except Exception: pass
    return urllib.parse.urlparse(url).netloc

WMO = {0:"☀️",1:"🌤️",2:"⛅",3:"☁️",45:"🌫️",48:"🌫️",51:"🌦️",53:"🌦️",55:"🌧️",56:"🌧️",57:"🌧️",61:"🌦️",63:"🌧️",65:"🌧️",66:"🌧️",67:"🌧️",71:"🌨️",73:"🌨️",75:"❄️",77:"❄️",80:"🌦️",81:"🌧️",82:"⛈️",85:"🌨️",86:"🌨️",95:"⛈️",96:"⛈️",99:"⛈️"}

def fdist(m, units):
    return (f"{m*0.000621371:.1f} mi" if units == "imperial" else f"{m/1000:.2f} km")

def ftick(c, units):
    v = (c * 9 / 5 + 32) if units == "imperial" else c
    return str(int(round(v)))

def calc_safe(expr):
    if re.search(r"[^0-9a-zA-Z_+\-*/%()., ]", expr): return False
    return not re.search(r"\b(while|for|function|eval|window|document|this|new|fetch|import|alert|require)\b", expr)

def main():
    spec = json.load(open(sys.argv[1]))
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "widget.html")).read()
    units = spec.get("units", "metric")
    searxng = spec.get("searxng", SEARXNG)
    blocks_in = spec.get("blocks")
    if blocks_in is None and "places" in spec:  # legacy v1 shim
        stops = [dict(name=p["name"], page=p.get("page"), hint=p.get("hint") or spec.get("hint")) for p in spec["places"]]
        blocks_in = [{"type": "map", "mode": spec.get("mode", "car"), "hint": spec.get("hint"), "stops": stops}]
    if blocks_in is None:
        raise SystemExit("spec needs blocks[] (v2) or places[] (v1 legacy)")
    title = spec.get("title", "Map")

    stops, routes, chips = [], [], []
    stop_idx = {}
    photo_stats = {"wikipedia": 0, "searxng": 0, "commons": 0, "none": 0}
    notes = notes_global
    blocks_html = []

    for b in blocks_in:
        t = b.get("type")
        if t == "hero":
            blocks_html.append(f'<div class="hero"><div class="h">{H.escape(b.get("h",""))}</div><div class="s">{md(b.get("sub",""))}</div></div>')
        elif t == "text":
            blocks_html.append(f'<div class="blk md">{md(b.get("md",""))}</div>')
        elif t == "stats":
            cells = "".join(f'<div class="st"><div class="v">{H.escape(str(i.get("v","")))}</div><div class="l">{H.escape(str(i.get("l","")))}</div>'
                            + (f'<div class="d {"neg" if str(i.get("d","")).startswith(("-","▼")) else ""}">{H.escape(str(i.get("d","")))}</div>' if i.get("d") else "") + "</div>"
                            for i in b.get("items", []))
            blocks_html.append(f'<div class="blk stats">{cells}</div>')
        elif t == "chart":
            blocks_html.append(f'<div class="blk">{svg_chart(b.get("kind","bar"), b.get("labels",[]), b.get("values",[]), b.get("unit",""))}</div>')
        elif t == "table":
            th = "".join(f"<th>{H.escape(str(c))}</th>" for c in b.get("headers", []))
            tr = "".join("<tr>" + "".join(f"<td>{H.escape(str(c))}</td>" for c in row) + "</tr>" for row in b.get("rows", []))
            blocks_html.append(f'<div class="blk"><table class="tb"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')
        elif t == "compare":
            cols = "".join(f'<div class="cm"><div class="h">{H.escape(c.get("h",""))}</div><ul>' + "".join(f"<li>{md(i)}</li>" for i in c.get("items", [])) + "</ul></div>" for c in b.get("columns", []))
            blocks_html.append(f'<div class="blk cmp">{cols}</div>')
        elif t == "steps":
            blocks_html.append('<div class="blk"><ol class="steps">' + "".join(f"<li>{md(i)}</li>" for i in b.get("items", [])) + "</ol></div>")
        elif t == "callout":
            blocks_html.append(f'<div class="co"><b>{H.escape(b.get("icon","💡"))} {H.escape(b.get("title",""))}</b>{md(b.get("md",""))}</div>')
        elif t == "quote":
            blocks_html.append(f"<blockquote>{md(b.get('md',''))}<cite>— {H.escape(b.get('cite',''))}</cite></blockquote>")
        elif t == "status":
            dots = {"ok": "#30a46c", "warn": "#f2a33c", "err": "#e5484d"}
            rows = "".join(f'<div class="sbr"><span class="dot" style="background:{dots.get(i.get("dot","ok"),"#30a46c")}"></span><b>{H.escape(i.get("label",""))}</b><span style="color:var(--muted-foreground)">{H.escape(i.get("note",""))}</span></div>' for i in b.get("items", []))
            blocks_html.append(f'<div class="blk sb">{rows}</div>')
        elif t == "links":
            cards = ""
            for it in b.get("items", []):
                url = it["url"]; ttl = it.get("title") or page_title(url)
                fav, dom = favicon(url)
                send = f"Open this page in the preview browser: {url}"
                cards += (f'<button class="lnk" data-hermes-send="{H.escape(send)}"><div class="shot" style="height:auto;padding:10px 12px;display:flex;gap:8px;align-items:center">'
                          f'{fav}<div><div class="t" style="font-size:12px">{H.escape(ttl[:70])}</div><div class="s">{H.escape(dom)}</div></div></div></button>')
                notes.append(f"link title fetched: {dom}")
            blocks_html.append(f'<div class="blk row">{cards}</div>')
        elif t == "weather":
            lat, lon = b.get("lat"), b.get("lon")
            if lat is None or lon is None: lat, lon = geocode(b.get("place", ""), b.get("hint", ""))
            w = get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
                "latitude": round(lat, 4), "longitude": round(lon, 4),
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "timezone": "auto", "forecast_days": b.get("days", 5)}))
            d = w["daily"]; cards = ""
            for i in range(len(d["time"])):
                wd = d["time"][i][5:].replace("-", "/")
                cards += (f'<div class="wc"><div class="l">{wd}</div><div class="e">{WMO.get(d["weather_code"][i], "🌡️")}</div>'
                          f'<div><span class="hi">{ftick(d["temperature_2m_max"][i], units)}°</span> <span class="lo">{ftick(d["temperature_2m_min"][i], units)}°</span></div>'
                          f'<div class="p">Precip {d["precipitation_probability_max"][i] or 0}%</div></div>')
            blocks_html.append(f'<h2>🌦️ {H.escape(b.get("place") or title)} 5-day forecast (open-meteo live)</h2><div class="wgrid">{cards}</div>')
            notes.append(f"weather ok: {b.get('place','')}")
        elif t == "stock":
            secs = ""
            for it in b.get("symbols", []):
                sym = it["sym"]; ranges = {}; chg1d = None
                for rg, iv in (("1d", "15m"), ("1m", "1d"), ("1y", "1wk")):
                    try:
                        j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={rg}&interval={iv}")["chart"]["result"][0]
                        cl = j["indicators"]["quote"][0].get("close") or []
                        cl = [c for c in cl if c is not None]
                        rngs = j["meta"].get("regularMarketPrice")
                        ranges[rg] = (cl, (cl[-1] - cl[0]) / cl[0] * 100 if len(cl) > 1 else 0.0)
                        if rg == "1d": chg1d = ranges["1d"][1]
                    except Exception: ranges[rg] = ([], None)
                px, c = ranges.get("1d", ([], None))
                last = px[-1] if px else None
                tabs = "".join(f'<button data-r="{r}"{" class=on" if r=="1d" else ""}>{r.upper()}</button>' for r in ("1d", "1m", "1y"))
                svgs = "".join(f'<svg data-r="{r}" viewBox="0 0 100 40">{spark(ranges[r][0])}</svg>' for r in ("1d", "1m", "1y"))
                neg = " neg" if (chg1d or 0) < 0 else ""
                chgtxt = f"{(chg1d or 0):+.2f}%"
                secs += (f'<div class="sc"><div class="hd"><div><b>{H.escape(it.get("name") or sym)}</b> <span class="s">{H.escape(sym)}</span></div>'
                         f'<div class="px">{f"{last:,.2f}" if last else "—"} <span class="ch{neg}">{chgtxt} (1d)</span></div></div>'
                         f'<div class="rg">{tabs}</div>{svgs}</div>')
                notes.append(f"stock {sym}: ranges ok={sum(1 for r in ranges.values() if r[0])}/3")
            blocks_html.append(f'<h2>📈 Live quotes (Yahoo, fetched at answer time)</h2>{secs}')
        elif t == "budget":
            rows = "".join(f'<div class="brow"><span style="min-width:110px">{H.escape(i["label"])}</span>'
                           f'<input type="range" min="0" max="200" value="100" data-i="{k}"><span class="c" style="min-width:60px;text-align:right">{i["cost"]:,}</span></div>'
                           for k, i in enumerate(b.get("items", [])))
            tot = sum(i["cost"] for i in b.get("items", []))
            blocks_html.append(f'<div class="bud"><b>💸 Budget sliders</b> (current total){rows}<div class="tot">Total <b>{tot:,}</b>{H.escape(b.get("currency",""))} <span class="warn"></span></div></div>')
            budget_js_data = json.dumps({"items": b.get("items", []), "cap": b.get("cap", 0), "per": bool(b.get("per_person"))})
            blocks_html[-1] = blocks_html[-1].replace('class="bud"', f'class="bud" data-bud=\'{budget_js_data}\'')
        elif t == "calculator":
            expr = b.get("expr", "")
            if not calc_safe(expr): raise SystemExit(f"calculator expr rejected: {expr}")
            rows = "".join(f'<div class="crow"><span style="min-width:110px">{H.escape(v.get("label",k))}</span>'
                           f'<input type="range" min="{v.get("min",0)}" max="{v.get("max",1000000)}" step="{v.get("step",1)}" value="{v.get("def",0)}" data-k="{k}">'
                           f'<span class="v" style="min-width:70px;text-align:right">{v.get("def",0)}</span></div>'
                           for k, v in b.get("vars", {}).items())
            calc_data = json.dumps({"expr": expr, "unit": b.get("unit", ""), "money": bool(b.get("money"))})
            blocks_html.append(f'<div class="calc" data-calc=\'{calc_data}\'><b>🧮 {H.escape(b.get("title","Calculator"))}</b>{rows}<div class="res">Result <b>—</b></div></div>')
        elif t == "email":
            send = f"Draft this email with the Gmail connector: subject '{b.get('subject','')}', outline: {b.get('body','(fill from this conversation)')}"
            blocks_html.append(f'<div class="blk"><button class="btn" data-hermes-send="{H.escape(send)}">✉️ Draft this email with Gmail</button></div>')
        elif t == "ics":
            blocks_html.append('<div class="blk"><button class="btn" data-hermes-send="__ICS_SEND__">📅 Add itinerary to calendar (.ics file)</button></div>')
        elif t == "sources":
            schips = ""
            for s in b.get("items", []):
                fav, dom = favicon(s["url"])
                send = f"Open this page in the preview browser: {s['url']}"
                schips += f'<button data-hermes-send="{H.escape(send)}">{fav}{H.escape(s.get("title", dom))}</button>'
            blocks_html.append(f'<div class="blk srcs"><span class="attr">Sources:</span>{schips}</div>')
        elif t == "images":
            cards = ""
            for k, it in enumerate(b.get("items", [])):
                nm = it.get("name") or it.get("query")
                u, wm, prov = photo(nm, it.get("page"), searxng)
                photo_stats[prov] += 1
                img = f'<img src="{H.escape(u)}" alt="" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="ph" style="display:none">Image failed</div>' if u else '<div class="ph">No photo</div>'
                send = (f"Open this page in the preview browser: {wm}" if wm else f"Find and open a source page for: {nm}")
                cards += f'<button class="card" data-hermes-send="{H.escape(send)}"><div class="shot">{img}</div><div class="meta"><div class="t">{H.escape(nm)}</div><div class="s">{prov}</div></div></button>'
            blocks_html.append(f'<div class="blk row">{cards}</div>')
        elif t == "map":
            hint = b.get("hint")
            placed = []  # (idx_in_stops, candidate list) for consensus fix
            base = len(stops)
            for s in b.get("stops", []):
                lat, lon = s.get("lat"), s.get("lon")
                cands = None
                if lat is None:
                    cands = geocode_candidates(s["name"], s.get("hint") or hint, s.get("page"))
                    if not cands: raise SystemExit(f"geocode failed: {s['name']} — add 'page' (wiki article) or lat/lon")
                    lat, lon = cands[0]
                    NEAR.append((lat, lon))
                si = len(stops); stop_idx[s["name"]] = si
                if cands: placed.append((si, cands))
                stops.append({"name": s["name"], "lat": lat, "lon": lon, "route": None})
            if placed:
                allpts = [(x["lat"], x["lon"]) for x in stops]
                ml = sorted(p[0] for p in allpts)[len(allpts)//2]; mn = sorted(p[1] for p in allpts)[len(allpts)//2]
                for si, cands in placed:
                    if _d((stops[si]["lat"], stops[si]["lon"]), (ml, mn)) > 3.0:
                        best = min(cands, key=lambda p: _d(p, (ml, mn)))
                        if _d(best, (ml, mn)) <= 3.0:
                            notes_global.append(f"consensus re-geocode: {stops[si]['name']} moved to nearest-cluster candidate")
                            stops[si]["lat"], stops[si]["lon"] = best
                        else:
                            notes_global.append(f"WARNING {stops[si]['name']} far from itinerary cluster — set explicit lat/lon or page")
            for k, s in enumerate(b.get("stops", [])):
                st = stops[base + k]; si = base + k
                rating = f' ★{s["rating"]}' if s.get("rating") else ""
                price = f'　{s["price"]}' if s.get("price") else ""
                area = s.get("area", "")
                tags = "".join(f'<span class="tag">{H.escape(tg)}</span>' for tg in s.get("tags", []))
                u, wm, prov = photo(s["name"], s.get("page"), searxng)
                photo_stats[prov] += 1
                img = f'<img src="{H.escape(u)}" alt="" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="ph" style="display:none">Image failed</div>' if u else '<div class="ph">No photo</div>'
                send = (f"Open this page in the preview browser: {wm}" if wm else f"Find and open an info page for: {s['name']}")
                st["card"] = (f'<button class="card" data-hermes-send="{H.escape(send)}"><div class="shot">{img}<span class="num">{si+1}</span></div>'
                              f'<div class="meta"><div class="t">{H.escape(s["name"])}</div><div class="r">{rating.strip()}{price}{area and " · " + H.escape(area) or ""}</div>'
                              f'<div class="tags">{tags}</div></div></button>')
            rt_defs = b.get("routes") or [{"label": None, "mode": b.get("mode", "car")}]
            mode0 = b.get("mode", "car")
            cards, first = "", True
            for ri, rd in enumerate(rt_defs):
                names = rd.get("stops") or [s["name"] for s in b["stops"]]
                idxs = [stop_idx[n] for n in names if n in stop_idx]
                for i in idxs: stops[i]["route"] = ri
                color = PALETTE[ri % len(PALETTE)]
                geo = None
                if len(idxs) >= 2:
                    try:
                        r = osrm([(stops[i]["lat"], stops[i]["lon"]) for i in idxs], rd.get("mode") or mode0)
                        geo = r["geometry"]
                        lbl = rd.get("label") or "Route"
                        chips.append(f'<span class="chip">🧭 {H.escape(lbl)} {fdist(r["distance"], units)} ⏱️ {int(r["duration"])//60} min</span>')
                        notes.append(f"route[{ri}] {int(r['distance'])}m {int(r['duration'])}s")
                    except Exception as e:
                        geo = {"type": "LineString", "coordinates": [[stops[i]["lon"], stops[i]["lat"]] for i in idxs]}
                        notes.append(f"route[{ri}] OSRM FAILED ({e}) -> straight-line fallback (segment drawn as a straight line)")
                routes.append({"label": rd.get("label") or f"Route {ri+1}", "color": color, "idxs": idxs, "geo": geo})
            cards = "".join(s["card"] for s in stops if "card" in s)
            multi = len(routes) > 1
            tabs = '<div class="tabs">' + "".join(f'<button data-tab="{ri}"{" class=on" if ri==0 else ""}>{H.escape(r["label"])}</button>' for ri, r in enumerate(routes)) + f'<button data-tab="-1">All</button></div>' if multi else ""
            gmaps = "https://www.google.com/maps/dir/" + "/".join(f"{s['lat']},{s['lon']}" for s in stops)
            coord_str = ";".join(f"{s['lat']},{s['lon']}" for s in stops)
            apples = "https://maps.apple.com/?dirflg=d&saddr=" + urllib.parse.quote(f"{stops[0]['lat']},{stops[0]['lon']}") + "&daddr=" + urllib.parse.quote(f"{stops[-1]['lat']},{stops[-1]['lon']}")
            gp = f'Export the route "{title}" (order: {", ".join(s["name"] for s in stops)}; coords {coord_str}) as a GPX file for me'
            gmap_app = spec.get("map_app", "google")
            open_btns = ""
            for app, send in (("Google Maps", f"Open this page in the preview browser: {gmaps}"), ("Apple Maps", f"Open this page in the preview browser: {apples}"),
                              ("OSM", f"Open this page in the preview browser: https://www.openstreetmap.org/directions?route={urllib.parse.quote(coord_str.replace(';', '%20'))}"), ("GPX", gp)):
                open_btns += f'<button data-hermes-send="{H.escape(send)}">{app}</button>'
            ics_btn = '<button data-hermes-send="__ICS_SEND__">📅 Add to calendar (.ics)</button>'
            map_html = (f'<div class="blk">{tabs}<div id="map" style="height:{spec.get("map_h",400)}px"></div>'
                        f'<div class="foot">{open_btns}{ics_btn}<span class="attr">Map © OpenStreetMap · Tiles © OpenFreeMap · Routing OSRM</span></div></div>')
            blocks_html.append(f'<div class="blk row">{cards}</div>' + map_html)
        elif t == "timeline":
            lis = ""
            tl_for_ics = []
            for it in b.get("items", []):
                ds = f' data-stop="{stop_idx[it["place"]]}"' if it.get("place") in stop_idx else ""
                dr = ""
                if it.get("place") in stop_idx and stops[stop_idx[it["place"]]]["route"] is not None:
                    dr = f' data-route="{stops[stop_idx[it["place"]]]["route"]}"'
                lis += f'<li{ds}{dr}><span class="tm">{H.escape(it.get("time",""))}</span><div><b>{H.escape(it.get("title", it.get("place","")))}</b>{md(it.get("md",""))}</div></li>'
                c = stops[stop_idx[it["place"]]] if it.get("place") in stop_idx else None
                tl_for_ics.append({"time": it.get("time"), "title": it.get("title") or it.get("place"), "place": it.get("place"),
                                   "lat": c["lat"] if c else None, "lon": c["lon"] if c else None})
            blocks_html.append(f'<h2>🕐 Timeline</h2><ul class="tl">{lis}</ul>')
            globals()["_tl_ics"] = tl_for_ics
    # ICS button (needs timeline data)
    tl = globals().get("_tl_ics", [])
    ics_send = f"Export this itinerary as a .ics calendar file for me: {json.dumps(tl, ensure_ascii=False)[:1200]}"
    out = (tpl.replace("__TITLE__", H.escape(title))
              .replace("__CHIPS__", "".join(chips))
              .replace("__BLOCKS__", "".join(blocks_html))
              .replace("__MAPBLOCK__", "")
              .replace("__ICS_SEND__", H.escape(ics_send))
              .replace("__STOPS__", json.dumps(stops, ensure_ascii=False))
              .replace("__ROUTES__", json.dumps(routes, ensure_ascii=False))
              .replace("__CENTER_LON__", str(stops[0]["lon"]) if stops else "121.5")
              .replace("__CENTER_LAT__", str(stops[0]["lat"]) if stops else "25.0")
              .replace("__FOLLOWS__", "".join(f'<button data-hermes-send="{H.escape(q)}">{H.escape(q)}</button>' for q in spec.get("followups", []))))
    js_src = re.findall(r"<script>(.*?)</script>", out, re.S)[-1]
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "_gw_check.js")
    open(tmp, "w").write(js_src)
    chk = subprocess.run("node --check " + tmp, shell=True, capture_output=True, text=True)
    if chk.returncode != 0: raise SystemExit("SYNTAX ERROR:\n" + chk.stderr[:600])
    open(sys.argv[2], "w").write(out)
    print(f"OK -> {os.path.abspath(sys.argv[2])} stops={len(stops)} routes={len(routes)} photos={photo_stats}")
    for n in notes: print("  " + n)

if __name__ == "__main__":
    main()
