#!/bin/bash
# Installs the Craft apps that are not in the linuxserver image (WordCraft, GridCraft, DeckCraft, CADCraft, SoundCraft,
# ArtCraft Launcher) into ./config/apps, adds desktop icons, and starts the Intelligent WebUI Craft bridge on every login.
set -e
cd "$(dirname "$0")"
CF=./config
mkdir -p $CF/apps $CF/craft-bridge $CF/.local/share/applications $CF/.local/share/icons $CF/Desktop
for r in wordcraft gridcraft deckcraft cadcraft soundcraft craft-launcher; do
  url=$(curl -s https://api.github.com/repos/storytold/$r/releases/latest | python3 -c 'import sys,json
d=json.load(sys.stdin); print(next(a["browser_download_url"] for a in d["assets"] if a["name"].endswith("linux-x86_64.tar.gz")))')
  a=$([ $r = craft-launcher ] && echo artcraft-launcher || echo $r)
  echo "installing $a"; rm -rf $CF/apps/$a; mkdir -p $CF/apps/$a
  curl -sfL "$url" | tar -xz -C $CF/apps/$a --strip-components=1
  sed -E "s#^Exec=$a#Exec=/config/apps/$a/bin/$a#" $CF/apps/$a/share/applications/ai.storyteller.$a.desktop > $CF/.local/share/applications/ai.storyteller.$a.desktop
  cp $CF/.local/share/applications/ai.storyteller.$a.desktop $CF/Desktop/
  cp -r $CF/apps/$a/share/icons/. $CF/.local/share/icons/ 2>/dev/null || true
done
chmod +x $CF/Desktop/*.desktop
cp ../craft-bridge/bridge.py $CF/craft-bridge/bridge.py
AS=$CF/.config/labwc/autostart
if [ -f $AS ] && ! grep -q craft-bridge $AS; then
  printf '\n# Intelligent WebUI craft bridge (internal network only)\nnohup /lsiopy/bin/python3 /config/craft-bridge/bridge.py >/config/craft-bridge/bridge.log 2>&1 &\n' >> $AS
fi
docker exec -d -u abc -e HOME=/config -w /config craft-apps /lsiopy/bin/python3 /config/craft-bridge/bridge.py
sleep 2
echo "Bridge token for the Intelligent UI valve craft_bridge_token is in: $CF/.craft-bridge-token"
