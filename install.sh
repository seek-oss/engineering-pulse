#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# engineering-pulse — installer
#
# Usage (one-liner):
#   curl -fsSL https://raw.githubusercontent.com/harryzhu2011/engineering-pulse/main/install.sh | bash
#
# Or run locally after cloning:
#   bash install.sh
# ────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
BOLD="\033[1m"
DIM="\033[2m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RESET="\033[0m"

info()    { echo -e "  ${CYAN}→${RESET}  $*"; }
success() { echo -e "  ${GREEN}✓${RESET}  $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "  ${RED}✗${RESET}  $*" >&2; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }
divider() { echo -e "${DIM}────────────────────────────────────────────────────${RESET}"; }

# Vivid “what to do next” (works when stdin is a pipe — e.g. curl | bash)
MAGENTA="\033[0;35m"
post_install_guide() {
  local ex="$INSTALL_DIR/.env.example"
  echo ""
  echo -e "${YELLOW}${BOLD}╔══════════════════════════════════════════════════════════════════════════════╗${RESET}"
  echo -e "${YELLOW}${BOLD}║  NEXT — finish setup (no secrets were prompted; curl | bash cannot ask you) ║${RESET}"
  echo -e "${YELLOW}${BOLD}╚══════════════════════════════════════════════════════════════════════════════╝${RESET}"
  echo ""
  echo -e "  ${BOLD}1) Credentials & API keys${RESET} ${CYAN}(required)${RESET}"
  echo -e "     Edit: ${MAGENTA}${BOLD}${ENV_FILE}${RESET}"
  if [ -f "$ex" ]; then
    echo -e "     ${DIM}Template with every variable explained:${RESET} ${MAGENTA}${ex}${RESET}"
  fi
  echo -e "     ${DIM}GitHub PAT, Datadog keys, dashboard URLs, SMTP, optional Todoist — see comments in .env.example.${RESET}"
  echo ""
  echo -e "  ${BOLD}2) Dashboard workflow (Cursor agent)${RESET}"
  echo -e "     Main prompt the scheduler runs: ${MAGENTA}${BOLD}${INSTALL_DIR}/prompts/daily-dashboard.md${RESET}"
  echo -e "     ${DIM}Change steps, metrics, or report layout by editing that file (or ask Cursor @-mention it).${RESET}"
  echo ""
  echo -e "  ${BOLD}3) Customise for your Datadog dashboards${RESET}"
  echo -e "     Read: ${MAGENTA}${BOLD}${INSTALL_DIR}/CUSTOMISING.md${RESET}"
  echo -e "     ${DIM}Plain-language template to paste into Cursor; no script changes required.${RESET}"
  echo ""
  echo -e "  ${BOLD}4) Schedule (LaunchAgent)${RESET}"
  echo -e "     ${DIM}Installed plist:${RESET} ${MAGENTA}${BOLD}${PLIST_PATH}${RESET}"
  echo -e "     ${DIM}Default run times come from${RESET} ${BOLD}SCHEDULE_HOURS${RESET}${DIM} (${SCHEDULE_HOURS}) when you run this installer.${RESET}"
  echo -e "     ${DIM}To change times: edit the plist (duplicate${RESET} ${BOLD}StartCalendarInterval${RESET} ${DIM}dicts), then:${RESET}"
  echo -e "       ${CYAN}launchctl unload \"${PLIST_PATH}\" && launchctl load \"${PLIST_PATH}\"${RESET}"
  echo -e "     ${DIM}Or re-run this installer from a clone with${RESET} ${BOLD}SCHEDULE_HOURS=\"9 12 17\" bash install.sh${RESET}"
  echo ""
  echo -e "  ${BOLD}5) Run once after .env is filled${RESET}"
  echo -e "     ${CYAN}bash ${RUNNER_SCRIPT}${RESET}"
  echo -e "     ${DIM}Logs:${RESET} ${CYAN}tail -f ${LOG_FILE}${RESET}"
  echo ""
  divider
}

# ── Config ───────────────────────────────────────────────────────────────────
REPO_URL="${REPO_URL:-https://github.com/harryzhu2011/engineering-pulse.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.engineering-pulse}"
BIN_DIR="${BIN_DIR:-$HOME/bin}"
RUNNER_SCRIPT="$BIN_DIR/run-daily-dashboard.sh"
PLIST_LABEL="com.$(whoami).daily-dashboard"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_FILE="/tmp/daily-dashboard.log"
SCHEDULE_HOURS="${SCHEDULE_HOURS:-8 10 18}"  # space-separated

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  Engineering Pulse — Installer${RESET}"
echo -e "${DIM}  Daily engineering dashboard (Datadog + GitHub), scheduled & emailed${RESET}"
divider

# ── 1. Prerequisite checks ───────────────────────────────────────────────────
header "1/5  Checking prerequisites"

check_cmd() {
  if command -v "$1" &>/dev/null; then
    success "$1  $(command -v "$1")"
  else
    error "$1 not found — $2"
    exit 1
  fi
}

check_cmd git  "install via https://git-scm.com"

# Python 3.11+
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
    success "python3  $PY_VER  ($(command -v python3))"
  else
    error "python3 $PY_VER found but 3.11+ is required"
    error "Install via: brew install python@3.12"
    exit 1
  fi
else
  error "python3 not found — install via https://python.org or 'brew install python@3.12'"
  exit 1
fi

# Cursor agent CLI (optional but warn loudly)
if command -v agent &>/dev/null; then
  success "cursor agent CLI  $(command -v agent)"
else
  warn "'agent' CLI not found in PATH"
  warn "The scheduled runner uses 'agent -p --trust --force ...'"
  warn "Make sure Cursor's CLI is installed and in PATH before the schedule runs."
  warn "Usually at: /usr/local/bin/agent  or  /Applications/Cursor.app/.../agent"
fi

# macOS launchd (expected on macOS only)
if [[ "$(uname)" != "Darwin" ]]; then
  warn "This installer sets up a macOS LaunchAgent — skipping on $(uname)"
  SKIP_LAUNCHD=1
else
  SKIP_LAUNCHD=0
fi

# ── 2. Clone or update repo ───────────────────────────────────────────────────
header "2/5  Installing repository"

if [ -d "$INSTALL_DIR/.git" ]; then
  info "Existing install found at $INSTALL_DIR — updating"
  git -C "$INSTALL_DIR" pull --ff-only
  success "Updated to $(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
else
  info "Cloning into $INSTALL_DIR"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  success "Cloned $(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
fi

# Create output directory
mkdir -p "$INSTALL_DIR/output"

# Set up Python venv
info "Creating Python virtual environment"
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
success "Python dependencies installed"

# ── 3. Seed .env (non-interactive — safe for curl | bash) ───────────────────
header "3/5  Configuration"

ENV_FILE="$INSTALL_DIR/.env"
EXAMPLE_ENV="$INSTALL_DIR/.env.example"

# Interactive prompts are intentionally omitted: when stdin is a pipe, `read` would
# consume this script’s own source and skip commands (e.g. qi=…), breaking the install.
if [ -f "$ENV_FILE" ]; then
  info "Keeping existing $ENV_FILE (edit it with your real credentials)"
else
  if [ -f "$EXAMPLE_ENV" ]; then
    cp "$EXAMPLE_ENV" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    success "Created $ENV_FILE from .env.example — replace every placeholder next"
  else
    warn ".env.example not found in clone — creating empty $ENV_FILE"
    : > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
  fi
fi

# ── 4. Shell runner script ────────────────────────────────────────────────────
header "4/5  Installing runner script"

mkdir -p "$BIN_DIR"
# Shell-quote paths here; the heredoc only expands $qi / $ql so runner lines are not
# executed by the parent shell if delimiter parsing ever goes wrong.
qi=$(printf '%q' "$INSTALL_DIR")
ql=$(printf '%q' "$LOG_FILE")
cat > "$RUNNER_SCRIPT" <<EOF
#!/bin/zsh
# run-daily-dashboard.sh — generated by engineering-pulse install.sh
# Invokes the Cursor agent against the daily-dashboard prompt.

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$HOME/.local/bin:\$HOME/bin"

cd $qi || exit 1

# Ensure the Python venv is available (scripts are called directly by the prompt)
source $qi/.venv/bin/activate

echo "[\$(date)] Starting daily-dashboard run" >> $ql

agent -p --trust --force "\$(cat prompts/daily-dashboard.md)" >> $ql 2>&1

_ec=\$?
echo "[\$(date)] Finished — exit code \$_ec" >> $ql
exit \$_ec
EOF
chmod +x "$RUNNER_SCRIPT"
success "Runner script written to $RUNNER_SCRIPT"

# Add ~/bin to PATH hint
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  warn "$BIN_DIR is not in your PATH."
  warn "Add this to your ~/.zshrc or ~/.bashrc:"
  warn "  export PATH=\"\$HOME/bin:\$PATH\""
fi

# ── 5. LaunchAgent (macOS only) ──────────────────────────────────────────────
header "5/5  Setting up schedule (LaunchAgent)"

if [ "${SKIP_LAUNCHD}" = "1" ]; then
  warn "Skipping LaunchAgent setup (non-macOS system)"
  echo ""
  info "To run manually:"
  info "  bash $RUNNER_SCRIPT"
else
  mkdir -p "$HOME/Library/LaunchAgents"

  # Build StartCalendarInterval entries from SCHEDULE_HOURS
  INTERVAL_ENTRIES=""
  for H in $SCHEDULE_HOURS; do
    MIN=0
    # Special case: "18" means 18:30
    if [ "$H" = "18" ]; then MIN=30; fi
    INTERVAL_ENTRIES+="
      <dict>
        <key>Hour</key>
        <integer>${H}</integer>
        <key>Minute</key>
        <integer>${MIN}</integer>
      </dict>"
  done

  cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/zsh</string>
      <string>${RUNNER_SCRIPT}</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>${INTERVAL_ENTRIES}
    </array>

    <key>StandardOutPath</key>
    <string>/tmp/daily-dashboard-launchd.out</string>
    <key>StandardErrorPath</key>
    <string>/tmp/daily-dashboard-launchd.err</string>

    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/bin:${HOME}/.local/bin</string>
    </dict>
  </dict>
</plist>
EOF

  # Unload any previous version, then load
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  launchctl load "$PLIST_PATH"
  success "LaunchAgent loaded: $PLIST_LABEL"
  info "Schedule: runs at $(echo "$SCHEDULE_HOURS" | sed 's/ /:00, /g'):00 daily"
  info "Logs: $LOG_FILE"
  info "launchd stdout: /tmp/daily-dashboard-launchd.out"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
divider
echo ""
echo -e "  ${GREEN}${BOLD}Installation complete!${RESET}"
echo ""
echo -e "  ${BOLD}Quick reference:${RESET}"
echo -e "  ${DIM}Run now:${RESET}      bash $RUNNER_SCRIPT"
echo -e "  ${DIM}View logs:${RESET}    tail -f $LOG_FILE"
echo -e "  ${DIM}Edit config:${RESET}  nano $ENV_FILE"
echo -e "  ${DIM}Uninstall:${RESET}    bash $INSTALL_DIR/uninstall.sh"
echo -e "  ${DIM}Day-2 ops:${RESET}    cd $INSTALL_DIR && make help"
echo ""
post_install_guide
echo ""
