# Tests

**Regression tests** (no network; every outbound call is stubbed). Run inside the Open WebUI container, which already has the
dependencies:

```bash
docker cp frontier_ui.py open-webui:/tmp/ && docker cp tests/test_regressions.py open-webui:/tmp/
docker exec -e WEBUI_SECRET_KEY=x open-webui python3 /tmp/test_regressions.py /tmp/frontier_ui.py
```

Covers: missing SearXNG, blocked or failing image providers, API keys never reaching HTML or tool output, unit preferences,
default / disabled / failing routes and invalid coordinates, a malformed-JSON corpus and spec normalization, TextureCraft registration.

**Browser tests** (Chromium, Firefox, WebKit) render a real card inside an iframe sandboxed the way Open WebUI does it, and check
rendering, °F/°C and mi/km by locale, the copy-link sheet, popups to a page that sends Cross-Origin-Opener-Policy, the
same-origin path, GPX download, and graceful degradation with WebGL off or the map CDN blocked.

```bash
# card.html = the HTML body returned by render_frontier_ui for a spec with two maps and a weather block
docker run --rm --network host -v "$PWD:/w" -w /w mcr.microsoft.com/playwright:v1.56.0-noble \
  sh -c "npm i --no-save playwright@1.56.0 >/dev/null && node tests/test_browser.mjs card.html"
```
