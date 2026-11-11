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
Chain: Wikipedia REST summary -> Wikidata search+coords -> Nominatim.
Polite by design: custom UA, ~1s spacing, one backoff retry on 403/429.
"""
import sys, json, time, urllib.request, urllib.parse, urllib.error

UA = {"User-Agent": "Mozilla/5.0 (compatible; HermesGenUI/2.0 personal assistant)"}

def get(url, timeout=15, retry=True):
    req = urllib.request.Request(url, headers=UA)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
    except urllib.error.HTTPError as e:
        if retry and e.code in (403, 429):
            time.sleep(2.0)
            return get(url, timeout, retry=False)
        raise
    except Exception:
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

def main():
    global CC
    args = sys.argv[1:]
    if args[:1] == ["--cc"]:
        CC = args[1].lower()
        args = args[2:]
    for name in args:
        hit, res = None, None
        for fn in (wiki_coords, wikidata_coords, nominatim):
            try:
                hit = fn(name if fn is not wiki_coords else name.replace(" ", "_"))
            except Exception:
                hit = None
            if hit and in_country(hit):
                res = hit
                break
            time.sleep(0.6)
        if res:
            print(f"{name}\t{res[0]:.6f}\t{res[1]:.6f}\t{res[2]}")
        else:
            print(f"{name}\tFAILED — put nearest-town coords or drop the stop")
        time.sleep(1.1)

if __name__ == "__main__":
    main()
