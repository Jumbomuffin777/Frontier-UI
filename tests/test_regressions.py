"""Frontier UI regression tests (no network, no pytest needed).

Run inside the Open WebUI container (it already has pydantic, aiohttp and starlette):
    docker cp frontier_ui.py open-webui:/tmp/ && docker cp tests/test_regressions.py open-webui:/tmp/
    docker exec -e WEBUI_SECRET_KEY=x open-webui python3 /tmp/test_regressions.py /tmp/frontier_ui.py
Every outbound call is stubbed, so results are deterministic.
"""
import asyncio
import importlib.util
import json
import sys
import traceback

PATH = sys.argv[1] if len(sys.argv) > 1 else "frontier_ui.py"
spec = importlib.util.spec_from_file_location("fui", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

RESULTS = []


def test(fn):
    RESULTS.append(fn)
    return fn


def reset():
    m._IMG_CACHE.clear(); m._ROUTE_CACHE.clear(); m._DOWN.clear(); m._GEO_CACHE.clear()


WIKI_PAGE = {"query": {"pages": [{"index": 1, "title": "Kiyomizu-dera", "fullurl": "https://en.wikipedia.org/wiki/Kiyomizu-dera",
                                  "thumbnail": {"source": "https://upload.wikimedia.org/x/Kiyomizu.jpg"}}]}}
COMMONS_PAGE = {"query": {"pages": [{"index": 1, "title": "File:Kiyomizu-dera at dusk.jpg", "imageinfo": [{
    "thumburl": "https://upload.wikimedia.org/c/Kiyomizu_dusk.jpg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:K.jpg",
    "extmetadata": {"Artist": {"value": "<a>Jane</a>"}, "LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}]}}
OPENVERSE = {"results": [{"thumbnail": "https://api.openverse.org/t/kiyomizu.jpg", "title": "Kiyomizu-dera temple", "creator": "Bob",
                          "license": "by", "foreign_landing_url": "https://flickr.com/x", "tags": []}]}
OSRM_OK = {"code": "Ok", "routes": [{"geometry": {"coordinates": [[135.785, 34.995], [135.78, 35.0], [135.775, 35.004]]},
                                     "distance": 1800, "duration": 1500}]}


class Calls(list):
    def hosts(self):
        return [u.split("/")[2] for u in self]


def stub_get_json(table, calls):
    """table: url-substring -> dict response or Exception instance."""
    async def fake(session, url, params=None, timeout=6):
        calls.append(url)
        for k, v in table.items():
            if k in url:
                if isinstance(v, Exception):
                    raise v
                return v
        raise RuntimeError(f"{url} 404")
    return fake


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def no_geocode(session, q, bias=None):
    return None


m._geocode = no_geocode  # geocoding is not under test; places keep the coordinates the model gave


# ---------------- User 1: no SearXNG, blocked providers ----------------
@test
def missing_searxng_place_cards_still_get_photos():
    reset(); calls = Calls()
    m._get_json = stub_get_json({"searxng": RuntimeError("Cannot connect to host searxng:8080"),
                                 "en.wikipedia.org": WIKI_PAGE, "commons.wikimedia.org": COMMONS_PAGE}, calls)
    spec = {"blocks": [{"type": "places", "items": [{"name": "Kiyomizu-dera", "rating": 4.7}]}]}
    run(m._resolve(spec, "http://searxng:8080", True, False, {}))
    c = spec["blocks"][0]["items"][0]["candidates"]
    assert c and c[0]["src"].startswith("https://upload.wikimedia.org/"), c
    assert "searxng" in m._DOWN, "unreachable SearXNG must be marked down"
    calls.clear()
    m._IMG_CACHE.clear()
    run(m._resolve({"blocks": [{"type": "places", "items": [{"name": "Kiyomizu-dera"}]}]}, "http://searxng:8080", True, False, {}))
    assert "searxng:8080" not in calls.hosts(), "a down SearXNG is skipped for a while"


@test
def empty_searxng_url_uses_keyless_sources():
    reset(); calls = Calls()
    m._get_json = stub_get_json({"en.wikipedia.org": WIKI_PAGE, "commons.wikimedia.org": COMMONS_PAGE}, calls)
    spec = {"blocks": [{"type": "images", "items": [{"query": "Kiyomizu-dera"}]}, {"type": "hero", "image": "Kiyomizu-dera"}]}
    run(m._resolve(spec, "", True, False, {}))
    assert spec["blocks"][0]["items"][0]["candidates"], "gallery"
    assert spec["blocks"][1]["candidates"], "hero"
    credits = [x.get("credit") for x in spec["blocks"][0]["items"][0]["candidates"] if x.get("credit")]
    assert any("CC BY-SA" in c for c in credits), "Commons attribution kept"


@test
def blocked_wikimedia_falls_back_to_openverse():
    reset(); calls = Calls()
    m._get_json = stub_get_json({"wikipedia.org": RuntimeError("403"), "wikimedia.org": RuntimeError("429"),
                                 "api.openverse.org": OPENVERSE}, calls)
    out = run(m._images_for(None, "", "Kiyomizu-dera temple", True, {}))
    assert out and out[0]["provider"] == "openverse", out


@test
def every_provider_down_returns_empty_without_raising():
    reset(); calls = Calls()
    m._get_json = stub_get_json({}, calls)  # everything 404s
    spec = {"blocks": [{"type": "places", "items": [{"name": "Nowhere Cafe"}]}]}
    run(m._resolve(spec, "http://searxng:8080", True, False, {}))
    assert spec["blocks"][0]["items"][0]["candidates"] == []


@test
def keyed_provider_errors_never_contain_the_key():
    class R:
        status = 403
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
    class S:
        def get(self, url, **kw): return R()
    try:
        run(m._keyed_json(S(), "https://www.googleapis.com/customsearch/v1", {"key": "SECRET123"}, {}))
        raise AssertionError("should raise")
    except RuntimeError as e:
        assert "SECRET123" not in str(e) and "googleapis" not in str(e), e


@test
def keyed_provider_used_first_when_selected_and_skipped_when_down():
    reset(); calls = Calls()
    async def fake_keyed(session, url, params, headers, timeout=6):
        calls.append(url)
        if "pexels" in url:
            return {"photos": [{"src": {"large": "https://images.pexels.com/p.jpg"}, "url": "https://pexels.com/p", "photographer": "Ann"}]}
        raise RuntimeError("HTTP 401")
    m._keyed_json = fake_keyed
    m._get_json = stub_get_json({"en.wikipedia.org": WIKI_PAGE, "commons.wikimedia.org": COMMONS_PAGE}, calls)
    out = run(m._images_for(None, "", "beach sunset", False, {"provider": "pexels", "pexels_key": "k"}))
    assert out[0]["provider"] == "pexels" and "Pexels" in out[0]["credit"], out
    reset(); calls.clear()
    out = run(m._images_for(None, "", "Kiyomizu-dera", True, {"provider": "brave", "brave_key": "bad"}))
    assert out and out[0]["provider"] in ("wikipedia", "commons") and "brave" in m._DOWN, out


@test
def keys_never_reach_the_html():
    reset()
    m._get_json = stub_get_json({}, Calls())
    t = m.Tools()
    t.valves.searxng_url = ""
    t.valves.brave_api_key = "BRAVEKEY999"; t.valves.pexels_api_key = "PEXKEY999"
    t.valves.google_api_key = "GKEY999"; t.valves.google_cx = "CX999"; t.valves.unsplash_access_key = "UNSKEY999"
    t.valves.embedding_url = ""
    resp, ctx = run(t.render_frontier_ui({"title": "x", "blocks": [{"type": "text", "md": "hi"}]}))
    html = resp.body.decode()
    for k in ("BRAVEKEY999", "PEXKEY999", "GKEY999", "CX999", "UNSKEY999"):
        assert k not in html and k not in ctx, k


def stub_by_query(hits, calls, delay=None):
    """Fake _get_json that answers Wikipedia searches by query text: hits = {query: n_results}; delay = {query: s}."""
    async def fake(session, url, params=None, timeout=6):
        q = (params or {}).get("gsrsearch", "").replace(" filetype:bitmap", "")
        calls.append(q)
        if delay and q in delay:
            await asyncio.sleep(delay[q])
        if "wikipedia.org" not in url:
            raise RuntimeError("404")
        n = hits.get(q, 0)
        return {"query": {"pages": [{"index": i, "title": q, "fullurl": f"https://en.wikipedia.org/wiki/{i}",
                                     "thumbnail": {"source": f"https://upload.wikimedia.org/{q.replace(' ', '_')}/{i}.jpg"}}
                                    for i in range(n)]}}
    return fake


@test
def long_gallery_query_tops_up_from_shorter_heads():  # PR #1
    reset(); calls = Calls()
    m._get_json = stub_by_query({"Coon cat": 3, "Maine Coon": 2}, calls)
    out = run(m._images_for(None, "", "brown tabby Maine Coon cat", True, {}, "Maine Coon - classic brown tabby"))
    assert len(out) >= 3 and all(o.get("fallback") for o in out), out


@test
def place_cards_never_fall_back_to_word_fragments():
    reset(); calls = Calls()
    m._get_json = stub_by_query({"Shibuya Tokyo": 5}, calls)
    out = run(m._images_for(None, "", "Ichiran Ramen Shibuya Tokyo", False, {}))
    assert out == [] and "Shibuya Tokyo" not in calls, (out, calls)


@test
def slow_fallback_keeps_what_the_query_found():
    reset(); calls = Calls()
    m._get_json = stub_by_query({"silver classic tabby Persian cat": 1, "Persian cat": 4}, calls, delay={"Persian cat": 30, "silver classic": 30})
    t = __import__("time").monotonic()
    out = run(asyncio.wait_for(m._images_for(None, "", "silver classic tabby Persian cat", True, {}), 8))
    assert len(out) == 1 and __import__("time").monotonic() - t < 8, out


# ---------------- User 1: units ----------------
@test
def units_default_auto_and_user_override():
    t = m.Tools()
    assert t._ui()["units"] == "auto"
    class UV:  # Open WebUI passes UserValves as a model instance
        units = "metric"; map_app = "osm"
    p = t._prefs({"valves": UV()})
    assert p == {"units": "metric", "map_app": "osm"}, p
    assert t._prefs({"valves": {"units": "default", "map_app": "default"}}) == {"units": "auto", "map_app": "google"}
    t.valves.units = "imperial"
    assert t._ui()["units"] == "imperial"
    assert "temperature_unit" not in m.Tools.Valves.model_fields


@test
def weather_is_fetched_metric():
    calls = []
    async def fake_weather(session, b, unit):
        calls.append(unit); return {"unit": "°C", "now": {"t": 20}}
    orig = m._weather; m._weather = fake_weather
    try:
        spec = {"blocks": [{"type": "weather", "location": "Ljubljana"}]}
        run(m._resolve(spec, "", False, False, {"live": True}))
        assert calls == ["celsius"], calls
    finally:
        m._weather = orig


# ---------------- User 2: routes ----------------
KYOTO = [{"name": "Kiyomizu-dera", "lat": 34.995, "lng": 135.785}, {"name": "Gion", "lat": 35.004, "lng": 135.775}]


def map_spec(**kw):
    return {"blocks": [{"type": "map", "places": [dict(p) for p in KYOTO], **kw}]}


@test
def single_day_route_is_on_by_default():
    reset(); calls = Calls()
    m._get_json = stub_get_json({"routing.openstreetmap.de": OSRM_OK, "router.project-osrm.org": OSRM_OK}, calls)
    s = map_spec(); run(m._resolve(s, "", False, True, {}))
    b = s["blocks"][0]
    assert b["route_geo"] and len(b["route_geo"]["line"]) == 3 and b["route_status"] == "", b
    assert any("routed-foot" in u for u in calls), "city-scale stops walk by default"


@test
def route_false_means_pins_only():
    reset(); calls = Calls()
    m._get_json = stub_get_json({"osrm": OSRM_OK, "openstreetmap.de": OSRM_OK}, calls)
    for off in (False, "false"):
        s = map_spec(route=off); run(m._resolve(s, "", False, True, {}))
        assert s["blocks"][0]["route_geo"] is None and not calls and s["blocks"][0]["route_status"] == ""


@test
def motorcycle_routes_by_road():
    reset(); calls = Calls()
    m._get_json = stub_get_json({"router.project-osrm.org": OSRM_OK}, calls)
    s = map_spec(mode="motorcycle"); run(m._resolve(s, "", False, True, {}))
    assert s["blocks"][0]["mode"] == "drive" and "router.project-osrm.org" in calls.hosts()
    assert s["blocks"][0]["route_geo"]["mode"] == "drive"


@test
def invalid_coordinates_are_reported():
    reset()
    m._get_json = stub_get_json({"osrm": OSRM_OK, "openstreetmap.de": OSRM_OK}, Calls())
    s = {"blocks": [{"type": "map", "places": [{"name": "A", "lat": 95, "lng": 10}, {"name": "B", "lat": "x", "lng": 1}]}]}
    run(m._resolve(s, "", False, True, {}))
    st = s["blocks"][0]["route_status"]
    assert "fewer than 2 stops with valid coordinates" in st and "2 stop(s) not placed" in st, st


@test
def routing_service_failure_is_reported_and_falls_back():
    reset(); calls = Calls()
    m._get_json = stub_get_json({"routed-foot": RuntimeError("x 502"), "routed-car": OSRM_OK}, calls)
    s = map_spec(); run(m._resolve(s, "", False, True, {}))
    b = s["blocks"][0]
    assert b["route_geo"]["mode"] == "drive", "foot router down -> car router backup"
    reset(); m._get_json = stub_get_json({}, Calls())
    s = map_spec(); run(m._resolve(s, "", False, True, {}))
    assert s["blocks"][0]["route_geo"] is None and "street route unavailable" in s["blocks"][0]["route_status"]


@test
def multi_day_routes_per_day():
    reset()
    m._get_json = stub_get_json({"osrm": OSRM_OK, "openstreetmap.de": OSRM_OK}, Calls())
    s = {"blocks": [{"type": "map", "days": [{"label": "Day 1", "places": [dict(p) for p in KYOTO]},
                                              {"label": "Day 2", "places": [dict(p) for p in KYOTO]}]}]}
    run(m._resolve(s, "", False, True, {}))
    assert all(s["blocks"][0]["day_routes"].values())


# ---------------- User 2: malformed JSON ----------------
GOOD = {"title": "T", "blocks": [{"type": "text", "md": "a"}]}
CORPUS = {
    "dict passed directly": GOOD,
    "plain string": json.dumps(GOOD),
    "code fence": "```json\n" + json.dumps(GOOD) + "\n```",
    "prose around": "Here is the card: " + json.dumps(GOOD) + " Hope it helps!",
    "trailing commas": '{"title":"T","blocks":[{"type":"text","md":"a",},],}',
    "smart quotes": '{\u201ctitle\u201d:\u201cT\u201d,\u201cblocks\u201d:[{\u201ctype\u201d:\u201ctext\u201d,\u201cmd\u201d:\u201ca\u201d}]}',
    "raw newline in string": '{"title":"T","blocks":[{"type":"text","md":"line1\nline2"}]}',
    "truncated": '{"title":"T","blocks":[{"type":"text","md":"a"}',
    "double encoded": json.dumps(json.dumps(GOOD)),
    "python literal": "{'title': 'T', 'blocks': [{'type': 'text', 'md': 'a'}], 'x': True}",
}


@test
def malformed_json_corpus_is_repaired():
    for name, raw in CORPUS.items():
        try:
            data, _ = m._normalize_spec(m._loads_lenient(raw))
        except Exception as e:
            raise AssertionError(f"{name}: {e}")
        assert data["blocks"][0]["type"] == "text", name


@test
def shapes_and_aliases_are_normalized():
    d, notes = m._normalize_spec({"spec": {"title": "T", "components": [{"type": "gallery", "items": [{"query": "x"}]},
                                                                        {"type": "fancy", "md": "kept"}, {"type": "nope"}]}})
    assert [b["type"] for b in d["blocks"]] == ["images", "text"], d
    assert any("components" in n for n in notes) and any("dropped" in n for n in notes), notes
    d, _ = m._normalize_spec([{"type": "text", "md": "a"}])
    assert d["blocks"][0]["md"] == "a"


@test
def literal_backslash_n_becomes_newlines():
    d, _ = m._normalize_spec({"blocks": [{"type": "map", "places": [{"name": "A", "note": "one\\ntwo"}]},
                                         {"type": "text", "md": "p1\\n\\np2"}]})
    assert d["blocks"][0]["places"][0]["note"] == "one\ntwo" and d["blocks"][1]["md"] == "p1\n\np2"
    d, _ = m._normalize_spec({"blocks": [{"type": "text", "md": "regex \\n stays\nbecause real newlines exist"}]})
    assert "\\n stays" in d["blocks"][0]["md"]


@test
def unrepairable_json_gives_actionable_error():
    for raw in ('{"title": "T", "blocks": [{"type": "text" "md": "a"}]}', "", "not json at all"):
        try:
            m._normalize_spec(m._loads_lenient(raw))
            raise AssertionError("should fail: " + repr(raw))
        except m.SpecError as e:
            msg = str(e)
            assert "spec" in msg and len(msg) < 400, msg
    try:
        m._normalize_spec({"title": "only a title"})
        raise AssertionError("should fail")
    except m.SpecError as e:
        assert "blocks" in str(e) and "Example" in str(e)


@test
def tool_returns_message_instead_of_raising():
    t = m.Tools()
    r = run(t.render_frontier_ui('{"title": "T", "blocks": [{"type": "text" "md": "a"}]}'))
    assert isinstance(r, str) and "invalid at character" in r, r


@test
def spec_parameter_schema_is_an_object():
    import inspect
    assert inspect.signature(m.Tools.render_frontier_ui).parameters["spec"].annotation is dict


# ---------------- TextureCraft ----------------
@test
def texturecraft_registered():
    assert "texturecraft" in m.CRAFT_APPS and m.CRAFT_EXT["glb"] == "texturecraft" and m.CRAFT_EXT["tcraft"] == "texturecraft"
    assert m.CRAFT_EXT["stl"] == "solidcraft"


if __name__ == "__main__":
    real_get, real_keyed = m._get_json, m._keyed_json
    failed = 0
    for fn in RESULTS:
        m._get_json, m._keyed_json = real_get, real_keyed
        try:
            fn(); print("PASS", fn.__name__)
        except Exception:
            failed += 1; print("FAIL", fn.__name__); traceback.print_exc()
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} passed")
    sys.exit(1 if failed else 0)
