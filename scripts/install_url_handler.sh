#!/usr/bin/env bash
# install_url_handler.sh — build and register "Engineering Pulse.app", the macOS handler
# for engineering-pulse:// links on the report calendar (Compare → "Ask the agent").
#
#   scripts/install_url_handler.sh [INSTALL_DIR]          # build + register
#   scripts/install_url_handler.sh --uninstall             # unregister + remove
#
# The app only forwards the link to scripts/run_compare.sh, which validates it.

set -euo pipefail

APP_DIR="${URL_HANDLER_APP_DIR:-$HOME/Applications}"
APP="$APP_DIR/Engineering Pulse.app"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

if [[ "${1:-}" == "--uninstall" ]]; then
  if [[ -d "$APP" ]]; then
    [[ -x "$LSREGISTER" ]] && "$LSREGISTER" -u "$APP" 2>/dev/null || true
    rm -rf "$APP"
    echo "Removed $APP"
  fi
  exit 0
fi

if [[ "$(uname)" != "Darwin" ]]; then
  echo "Link handler is macOS only; skipping." >&2
  exit 0
fi

INSTALL_DIR="$(cd "${1:-$(dirname "${BASH_SOURCE[0]}")/..}" && pwd)"
RUNNER="$INSTALL_DIR/scripts/run_compare.sh"
case "$RUNNER" in
  *\"* | *\\*) echo "Install path contains quotes or backslashes; cannot build link handler." >&2; exit 1 ;;
esac

src=$(mktemp -t engineering-pulse-handler).applescript
trap 'rm -f "$src"' EXIT
cat >"$src" <<EOF
on open location theURL
	do shell script "/bin/bash " & quoted form of "$RUNNER" & " --url " & quoted form of theURL & " >/dev/null 2>&1 &"
end open location

on run
	display dialog "Engineering Pulse link handler. Use the Compare view on the report calendar to ask the agent to compare two reports." buttons {"OK"} default button 1 with title "Engineering Pulse"
end run
EOF

mkdir -p "$APP_DIR"
rm -rf "$APP"
osacompile -o "$APP" "$src"

plist="$APP/Contents/Info.plist"
plutil -replace CFBundleIdentifier -string "com.$(whoami).engineering-pulse" "$plist"
plutil -replace LSUIElement -bool true "$plist"
plutil -replace CFBundleURLTypes -json \
  '[{"CFBundleURLName":"Engineering Pulse compare","CFBundleURLSchemes":["engineering-pulse"]}]' "$plist"
codesign --force --sign - "$APP" >/dev/null 2>&1 || true
"$LSREGISTER" -f "$APP"
echo "Registered engineering-pulse:// links → $APP"
