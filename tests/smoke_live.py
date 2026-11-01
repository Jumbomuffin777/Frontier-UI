import asyncio, importlib.util, json, sys, time
spec = importlib.util.spec_from_file_location("fui", "/tmp/frontier_ui.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
t = m.Tools(); t.valves.searxng_url = "http://searxng-missing:8080"; t.valves.embedding_url = ""
t.valves.tiles_url = sys.argv[1] if len(sys.argv) > 1 else ""
S = {"title": "Ljubljana day", "blocks": [
  {"type": "text", "md": "A compact walking day.\\n\\nStart early."},
  {"type": "images", "items": [{"query": "Ljubljana Triple Bridge"}, {"query": "Ljubljana Castle"}, {"query": "Lake Bled"}]},
  {"type": "map", "area": "Ljubljana, Slovenia", "places": [{"name": "Ljubljana Castle", "lat": 46.0489, "lng": 14.5087, "note": "Funicular up\\nViews"},
     {"name": "Triple Bridge", "lat": 46.0511, "lng": 14.5061}, {"name": "Tivoli Park", "lat": 46.0547, "lng": 14.4950}]},
  {"type": "places", "area": "Ljubljana", "items": [{"name": "Ljubljana Central Market", "rating": 4.6, "price": "$", "tags": ["Market"]},
     {"name": "Gostilna Sokol", "rating": 4.4, "price": "$$", "tags": ["Slovenian"]}, {"name": "Prešeren Square", "rating": 4.7, "price": "free", "tags": ["Square"]}]},
  {"type": "weather", "location": "Ljubljana, Slovenia", "days": 4},
  {"type": "map", "title": "Moto loop", "mode": "motorcycle", "places": [{"name": "Ljubljana", "lat": 46.0569, "lng": 14.5058}, {"name": "Bled", "lat": 46.3683, "lng": 14.1146}, {"name": "Bohinj", "lat": 46.2775, "lng": 13.8866}]}],
  "followups": ["Where to eat?"]}
t0 = time.time()
resp, ctx = asyncio.run(t.render_frontier_ui(json.dumps(S)))
html = resp.body.decode(); open("/tmp/card13.html", "w").write(html)
print("secs", round(time.time() - t0, 1)); print(ctx)
spec2 = m._CARDS[ctx.split("card id: ")[1].split(")")[0]]
for b in spec2["blocks"]:
    if b["type"] == "images": print("gallery", [(it.get("candidates") or [{}])[0].get("provider") for it in b["items"]])
    if b["type"] == "places": print("places", [(len(it.get("candidates") or []), (it.get("candidates") or [{}])[0].get("provider")) for it in b["items"]])
    if b["type"] == "map": print("map", b.get("mode"), bool(b.get("route_geo")), repr(b.get("route_status")), [p.get("note") for p in b["places"]][:1])
    if b["type"] == "weather": print("weather", (b.get("weather") or {}).get("unit"), (b.get("weather") or {}).get("wind_unit"))
    if b["type"] == "text": print("text", repr(b["md"]))
print("DOWN", list(m._DOWN))
