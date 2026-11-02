#!/bin/bash
# Installs the Craft apps that are not in the linuxserver image (WordCraft, GridCraft, DeckCraft, CADCraft, SoundCraft,
# TextureCraft, ArtCraft Launcher) into ./config/apps, adds desktop icons, and installs the Frontier UI Craft bridge,
# which then starts with the container (an s6 service from docker-compose.yml) - no manual docker exec after restarts.
set -e
cd "$(dirname "$0")"
CF=./config
mkdir -p $CF/apps $CF/craft-bridge $CF/.local/share/applications $CF/.local/share/icons $CF/Desktop
for r in storytold/wordcraft storytold/gridcraft storytold/deckcraft storytold/cadcraft storytold/soundcraft storytold/craft-launcher storytold/craft-anything storytold/texturecraft tangency-labs/solidcraft; do
  url=$(curl -s https://api.github.com/repos/$r/releases/latest | python3 -c 'import sys,json
d=json.load(sys.stdin); print(next(a["browser_download_url"] for a in d["assets"] if a["name"].endswith("linux-x86_64.tar.gz") and "-0" in a["name"] or a["name"].endswith("linux-x86_64.tar.gz")))')
  a=${r#*/}; [ $a = craft-launcher ] && a=artcraft-launcher
  echo "installing $a"; rm -rf $CF/apps/$a; mkdir -p $CF/apps/$a
  curl -sfL "$url" | tar -xz -C $CF/apps/$a --strip-components=1
  d=$(ls $CF/apps/$a/share/applications/*.desktop | head -1); b=$(basename $d)
  sed -E "s#^Exec=([a-z-]+)#Exec=/config/apps/$a/bin/\1#" $d > $CF/.local/share/applications/$b
  cp $CF/.local/share/applications/$b $CF/Desktop/
  cp -r $CF/apps/$a/share/icons/. $CF/.local/share/icons/ 2>/dev/null || true
done
chmod +x $CF/Desktop/*.desktop
cp ../craft-bridge/bridge.py $CF/craft-bridge/bridge.py
# The bridge runs as an s6 service defined in docker-compose.yml (configs: craft-bridge-service): it starts with the
# container and restarts if it stops. Containers created from an older compose file get it after a one-time recreate.
if ! docker exec craft-apps test -x /custom-services.d/craft-bridge 2>/dev/null; then
  echo "Recreating the container so it picks up the bridge service (one-time)..."; docker compose up -d --force-recreate
fi
sleep 8
docker exec craft-apps sh -c 'ps -eo args | grep -q "[c]raft-bridge/bridge.py"' && echo "Craft bridge is running." \
  || echo "Bridge not running yet: check 'docker logs craft-apps'."
echo "Bridge token for the Frontier UI valve craft_bridge_token is in: $CF/.craft-bridge-token"
