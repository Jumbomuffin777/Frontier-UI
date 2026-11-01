#!/bin/bash
# Usage: ./setup.sh /path/to/maps-dir [YYYYMMDD]
# Put the planet on a big disk: a spinning HDD is fine for one household (tiles are read with small range requests).
set -e
cd "$(dirname "$0")"
MAPS=${1:?maps dir}; DATE=${2:-$(date -u -d yesterday +%Y%m%d)}
mkdir -p www/maps/js www/maps/fonts www/maps/sprites craft "$MAPS"
PM=$(curl -s https://registry.npmjs.org/pmtiles/latest | python3 -c 'import sys,json;print(json.load(sys.stdin)["version"])')
BM=$(curl -s https://registry.npmjs.org/@protomaps/basemaps/latest | python3 -c 'import sys,json;print(json.load(sys.stdin)["version"])')
curl -sfL -o www/maps/js/maplibre-gl.js  https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.js
curl -sfL -o www/maps/js/maplibre-gl.css https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.css
curl -sfL -o www/maps/js/pmtiles.js      https://cdn.jsdelivr.net/npm/pmtiles@$PM/dist/pmtiles.js
curl -sfL -o www/maps/js/basemaps.js     https://cdn.jsdelivr.net/npm/@protomaps/basemaps@$BM/dist/basemaps.js
tmp=$(mktemp -d); curl -sfL https://github.com/protomaps/basemaps-assets/archive/refs/heads/main.tar.gz | tar -xz -C $tmp \
  --wildcards '*/fonts/Noto Sans Regular/*' '*/fonts/Noto Sans Medium/*' '*/fonts/Noto Sans Italic/*' '*/sprites/v4/*'
cp -r $tmp/*/fonts/* www/maps/fonts/; cp -r $tmp/*/sprites/v4 www/maps/sprites/; rm -rf $tmp
for r in storytold/photocraft storytold/vectorcraft storytold/filmcraft storytold/lightcraft storytold/pdfcraft storytold/effectcraft storytold/designcraft storytold/figcraft storytold/wordcraft storytold/gridcraft storytold/deckcraft storytold/cadcraft storytold/soundcraft storytold/craft-launcher storytold/craft-anything storytold/texturecraft tangency-labs/solidcraft; do
  url=$(curl -s https://api.github.com/repos/$r/releases/latest | python3 -c 'import sys,json
d=json.load(sys.stdin); print(next(a["browser_download_url"] for a in d["assets"] if "-web-" in a["name"] and a["name"].endswith(".zip")))')
  a=${r#*/}; [ $a = craft-launcher ] && a=launcher; rm -rf craft/$a; mkdir -p craft/$a; curl -sfL -o /tmp/$a.zip "$url"; unzip -q /tmp/$a.zip -d craft/$a; rm /tmp/$a.zip
  d=$(ls craft/$a); [ $(echo "$d" | wc -l) = 1 ] && [ -d craft/$a/$d ] && mv craft/$a/$d/* craft/$a/ && rmdir craft/$a/$d
done
echo "Downloading the Protomaps planet for $DATE (~140 GB, resumable)..."
curl -fL --retry 20 -C - -o "$MAPS/planet-$DATE.pmtiles" "https://build.protomaps.com/$DATE.pmtiles"
ln -sfn "planet-$DATE.pmtiles" "$MAPS/planet.pmtiles"
echo done
