# hermes-port — Frontier-UI for Hermes Agent

ChatGPT-style generative UI ported from Open WebUI (this repo) to Hermes Agent chat
(`::preview{file=...}` inline HTML widgets). MIT, same as upstream.

- Canonical source of truth: this directory. Synced to the live Hermes skill at
  `~/.hermes/skills/generative-ui-widgets/` via ./sync.sh
- Spec-driven: agent writes spec JSON -> scripts/build_widget.py fetches data
  (geocode/route/weather/stock/photos) -> renders widget.html -> delivered inline.
- Key difference vs upstream: Hermes inlines ::preview in a sandbox="allow-scripts"
  iframe (upstream issue #144361): anchors, window.open, blob downloads and clipboard
  are dead inside. EVERY interactive element therefore uses data-hermes-send and the
  agent executes the action (desktop_preview, .gpx/.ics file output, Gmail draft...).

Docs: docs/PORT_MAP.md (block-by-block port status), skill/SKILL.md (usage + pitfalls).
