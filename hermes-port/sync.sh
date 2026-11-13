#!/usr/bin/env bash
# Install/update the Hermes skill from this repo (repo is the source of truth).
#
#   ./sync.sh                 # copy into ${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/generative-ui-widgets
#   ./sync.sh /custom/dest    # explicit destination
#   ./sync.sh --prune [dest]  # also delete files in dest that are not in the repo (opt-in)
#
# Non-destructive by default: never deletes anything unless --prune is given, and
# --prune refuses to run against a directory that does not look like this skill.
set -euo pipefail

PRUNE=0
if [ "${1:-}" = "--prune" ]; then PRUNE=1; shift; fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skill"
DEST="${1:-${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/generative-ui-widgets}"

[ -f "$SRC/SKILL.md" ] || { echo "error: skill source not found at $SRC" >&2; exit 1; }
case "$DEST" in
  ""|"/"|"$HOME"|"$HOME/") echo "error: refusing unsafe destination '$DEST'" >&2; exit 1 ;;
esac

if [ "$PRUNE" = 1 ] && [ -d "$DEST" ] && [ -n "$(ls -A "$DEST")" ] && [ ! -f "$DEST/SKILL.md" ]; then
  echo "error: --prune target '$DEST' has no SKILL.md; refusing to delete its contents" >&2
  exit 1
fi

mkdir -p "$DEST"
if command -v rsync >/dev/null 2>&1; then
  if [ "$PRUNE" = 1 ]; then rsync -a --delete -- "$SRC/" "$DEST/"; else rsync -a -- "$SRC/" "$DEST/"; fi
else
  [ "$PRUNE" = 1 ] && echo "warning: rsync not found; --prune ignored" >&2
  cp -R -- "$SRC/." "$DEST/"
fi

[ -f "$DEST/SKILL.md" ] && [ -f "$DEST/scripts/build_widget.py" ] || { echo "error: install verification failed in $DEST" >&2; exit 1; }
echo "synced: $SRC -> $DEST"
