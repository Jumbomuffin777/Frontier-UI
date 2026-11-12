#!/usr/bin/env python3
"""Batch coordinate resolver — use BEFORE writing the spec for sites that
likely have no Wikipedia article (ruins, shrines, tunnels, viewpoints).
Prints one line per name: name<TAB>lat<TAB>lon<TAB>source. Feed the lat/lon
straight into spec stops to bypass live geocoding entirely.

Usage: python3 coords.py "Temple of the Sun" "Intihuatana Stone" ...
       python3 coords.py --cc tw "阿宗麵線" "蜂大咖啡" ...   # city/venue lookups
--cc <iso2> pins Nominatim to that country AND reverse-validates wiki/
wikidata hits, so name collisions ("西本願寺" -> Kyoto temple, "蜂大咖啡"
-> Shanghai) are rejected instead of poisoning the map. ALWAYS pass --cc
for venue/shop queries inside a known country.
--near "lat,lon" adds a cluster anchor: same-country-but-wrong-city hits
("龍山寺" -> the Kaohsiung one on a Taipei trip) don't end the tier chain
early; anything outside ~44km of the anchor is flagged "FAR from cluster".
Chain: Wikipedia REST summary -> Wikidata search+coords -> Nominatim.
Polite by design: custom UA, ~1s spacing, one backoff retry on 403/429.
"""
import sys, os, json, time, urllib.request, urllib.parse, urllib.error

UA = {"User-Agent": "Mozilla/5.0 (compatible; HermesGenUI/2.0 personal assistant)"}

# Persistent URL cache: repeated names across disambiguation rounds are free.
# Positive results keep 30 days; failures 15 min (wiki 403s are transient and
# made a previously-successful name FAILED on one field test).
CACHE = {}
CACHE_PATH = None
class _NegHit(Exception):
    pass

def _cache_init():
    global CACHE_PATH
    CACHE_PATH = os.environ.get("HERMES_COORDS_CACHE",
        os.path.join(os.path.expanduser("~"), ".cache", "hermes_gui_coords.json"))
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        if os.path.exists(CACHE_PATH):
            CACHE.update(json.load(open(CACHE_PATH)))
    except Exception:
        CACHE_PATH = None

def _cache_put(url, data=None, neg=False):
    if not CACHE_PATH:
        return
    CACHE[url] = {"t": time.time(), "exp": time.time() + (900 if neg else 30*86400),
                  "__neg": 1 if neg else 0, "d": data}
    try:
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(CACHE, f)
        os.replace(tmp, CACHE_PATH)
    except Exception:
        pass

def _cache_hit(url):
    v = CACHE.get(url)
    if not v or time.time() > v["exp"]:
        return None
    if v.get("__neg"):
        raise _NegHit(url)
    return v["d"]

def get(url, timeout=15, retry=True):
    if CACHE_PATH:
        hit = _cache_hit(url)
        if hit is not None:
            return hit
    req = urllib.request.Request(url, headers=UA)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
        _cache_put(url, data)
        return data
    except urllib.error.HTTPError as e:
        if retry and e.code in (403, 429):
            time.sleep(2.0)
            return get(url, timeout, retry=False)
        _cache_put(url, neg=True)
        raise
    except _NegHit:
        raise
    except Exception:
        _cache_put(url, neg=True)
        return None

def wiki_coords(page):
    for host in ("zh", "en"):
        s = get(f"https://{host}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page)}")
        c = (s or {}).get("coordinates")
        if c and c.get("lat") and c.get("lon"):
            return float(c["lat"]), float(c["lon"]), f"wiki:{host}"
    return None

def wikidata_coords(name):
    s = get("https://www.wikidata.org/w/api.php?action=query&format=json&origin=*&list=search"
            "&srsearch=" + urllib.parse.quote(name) + "&srnamespace=0&srlimit=3")
    titles = [h["title"] for h in ((s or {}).get("query") or {}).get("search", []) if h.get("ns") == 0]
    if not titles:
        return None
    q = get("https://www.wikidata.org/w/api.php?action=query&format=json&origin=*&prop=coordinates"
            "&titles=" + urllib.parse.quote("|".join(titles[:3])))
    for pg in ((q or {}).get("query") or {}).get("pages", {}).values():
        for c in pg.get("coordinates", []):
            try:
                return float(c["lat"]), float(c["lon"]), "wikidata"
            except (KeyError, ValueError):
                pass
    return None

CC = None

def in_country(p):
    if not CC:
        return True
    try:
        # NOTE: reverse ignores the countrycodes param — compare the returned
        # address.country_code ourselves.
        r = get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={p[0]}&lon={p[1]}&zoom=10")
        got = ((r or {}).get("address") or {}).get("country_code", "")
        return bool(r and r.get("lat")) and got.lower() == CC
    except Exception:
        return False

def nominatim(name):
    cc = f"&countrycodes={CC}" if CC else ""
    r = get("https://nominatim.openstreetmap.org/search?format=json&limit=1" + cc + "&q=" + urllib.parse.quote(name))
    if r:
        return float(r[0]["lat"]), float(r[0]["lon"]), "nominatim"
    return None

NEAR = None  # --near "lat,lon" cluster anchor

def near_ok(p):
    return not NEAR or (abs(p[0]-NEAR[0]) <= 0.4 and abs(p[1]-NEAR[1]) <= 0.4)  # ~44km

def main():
    global CC, NEAR
    args = sys.argv[1:]
    if args[:1] == ["--cc"]:
        CC = args[1].lower()
        args = args[2:]
    if args[:1] == ["--near"]:
        NEAR = tuple(float(x) for x in args[1].split(","))
        args = args[2:]
    _cache_init()
    for name in dict.fromkeys(args):  # dedup within one batch
        hit, res, far = None, None, None
        for fn in (wiki_coords, wikidata_coords, nominatim):
            try:
                hit = fn(name if fn is not wiki_coords else name.replace(" ", "_"))
            except Exception:
                hit = None
            if hit and in_country(hit):
                if near_ok(hit):
                    res = hit
                    break
                if far is None:
                    far = hit  # right country, wrong city — keep trying tiers
            time.sleep(0.6)
        if not res and far:
            res = far  # nothing near the cluster: surface it, but flag loudly
        if res:
            flag = "\tFAR from cluster — verify name or drop" if far is res and NEAR else ""
            print(f"{name}\t{res[0]:.6f}\t{res[1]:.6f}\t{res[2]}{flag}")
        else:
            print(f"{name}\tFAILED — put nearest-town coords or drop the stop")
        time.sleep(1.1)

if __name__ == "__main__":
    main()
