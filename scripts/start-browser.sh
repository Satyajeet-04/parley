#!/usr/bin/env bash
#
# Start Brave or Chrome with the Chrome DevTools Protocol (CDP) enabled so
# Parley can connect to it. Re-uses your normal profile so you stay logged in
# to ChatGPT, Gemini, Claude, etc.
#
# Usage:
#   ./scripts/start-browser.sh            # auto-detect Brave, then Chrome
#   BROWSER=chrome ./scripts/start-browser.sh
#   PARLEY_CDP_PORT=9333 ./scripts/start-browser.sh
#
set -euo pipefail

PORT="${PARLEY_CDP_PORT:-9222}"

find_browser() {
  if [[ -n "${BROWSER:-}" ]]; then
    command -v "$BROWSER" && return 0
  fi
  for b in brave-browser brave google-chrome google-chrome-stable chromium chromium-browser \
           "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
    if command -v "$b" >/dev/null 2>&1 || [[ -x "$b" ]]; then
      echo "$b"
      return 0
    fi
  done
  return 1
}

BIN="$(find_browser)" || {
  echo "No Brave/Chrome/Chromium binary found. Set BROWSER=/path/to/browser." >&2
  exit 1
}

echo "Launching: $BIN"
echo "CDP endpoint: http://localhost:${PORT}"
echo "Tip: leave this browser open; run 'parley.py list' in another terminal."

exec "$BIN" \
  --remote-debugging-port="${PORT}" \
  --remote-allow-origins=* \
  "$@"
