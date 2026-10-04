#!/usr/bin/env bash
# install_url_handler.sh — build and register "Engineering Pulse.app", the macOS handler
# for engineering-pulse:// links on the report calendar (Compare → "Ask the agent",
# Settings → "Apply") and in the red problems box of a report ("Sign in", "Re-run").
#
#   scripts/install_url_handler.sh [INSTALL_DIR]          # build + register
#   scripts/install_url_handler.sh --uninstall             # unregister + remove
#
# The app only forwards the link to scripts/run_compare.sh, scripts/settings.py or
# scripts/fix_link.py, which validate it; settings changes need a click on the app's own confirmation dialog.

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
SETTINGS="$INSTALL_DIR/scripts/settings.py"
FIX="$INSTALL_DIR/scripts/fix_link.py"
PY="$INSTALL_DIR/.venv/bin/python"
case "$INSTALL_DIR" in
  *\"* | *\\*) echo "Install path contains quotes or backslashes; cannot build link handler." >&2; exit 1 ;;
esac

src=$(mktemp -t engineering-pulse-handler).applescript
trap 'rm -f "$src"' EXIT
cat >"$src" <<EOF
on open location theURL
	if theURL starts with "engineering-pulse://settings" then
		applySettings(theURL)
	else if theURL starts with "engineering-pulse://auth" or theURL starts with "engineering-pulse://run" then
		fixLink(theURL)
	else
		do shell script "/bin/bash " & quoted form of "$RUNNER" & " --url " & quoted form of theURL & " >/dev/null 2>&1 &"
	end if
end open location

-- The dialog text comes from settings.py after validation, never from the raw link.
on applySettings(theURL)
	activate
	set cmd to quoted form of "$PY" & " " & quoted form of "$SETTINGS"
	try
		set summary to do shell script cmd & " describe-url " & quoted form of theURL
	on error errMsg
		display dialog errMsg buttons {"OK"} default button 1 with title "Engineering Pulse" with icon caution
		return
	end try
	if summary is "No changes." then
		display dialog "These settings are already in place." buttons {"OK"} default button 1 with title "Engineering Pulse"
		return
	end if
	display dialog "Apply these settings?" & return & return & summary buttons {"Cancel", "Apply"} default button "Apply" cancel button "Cancel" with title "Engineering Pulse"
	try
		do shell script cmd & " apply-url " & quoted form of theURL
	on error errMsg
		display dialog errMsg buttons {"OK"} default button 1 with title "Engineering Pulse" with icon stop
	end try
end applySettings

-- Red box buttons: fix_link.py validates the link (known agent, listed MCP server,
-- pulse/sprint only) before opening Terminal or starting a run.
on fixLink(theURL)
	try
		set msg to do shell script quoted form of "$PY" & " " & quoted form of "$FIX" & " handle " & quoted form of theURL
	on error errMsg
		activate
		display dialog errMsg buttons {"OK"} default button 1 with title "Engineering Pulse" with icon caution
		return
	end try
	if msg contains "already" then
		activate
		display dialog msg buttons {"OK"} default button 1 with title "Engineering Pulse"
	end if
end fixLink

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
