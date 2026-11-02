#!/bin/bash
# Rebuild frontier_ui.py from its parts:
#   p1, p2  Python: lookups (photos, geocoding, routes) and the resolver
#   p6      Python: live data, link previews, embeddings, Craft bridge, files & notes, exports
#   p3-p5   HTML / CSS / JS renderer (p7 = v1.1 blocks + action bar)
#   p9      the Tools class (valves and the four tool methods)
set -e
cd "$(dirname "$0")"
for f in p1.py p2.py p6.py p3.py p4.py p4b.py p7.py p5.py p9.py; do
    sed -e '1s/^\xef\xbb\xbf//' "$f" | tr -d '\r'
done > ../frontier_ui.py
python3 -m py_compile ../frontier_ui.py && echo "built ../frontier_ui.py"
