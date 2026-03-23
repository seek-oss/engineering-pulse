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

# ── 3. Configure .env ─────────────────────────────────────────────────────────
header "3/5  Configuration"

ENV_FILE="$INSTALL_DIR/.env"

if [ -f "$ENV_FILE" ]; then
  echo ""
  read -r -p "  .env already exists. Reconfigure? [y/N] " RECONFIG
  echo ""
  if [[ ! "$RECONFIG" =~ ^[Yy]$ ]]; then
    info "Keeping existing .env"
    SKIP_ENV=1
  else
    SKIP_ENV=0
  fi
else
  SKIP_ENV=0
fi

prompt_var() {
  local var="$1"
  local desc="$2"
  local example="$3"
  local required="${4:-yes}"
  local current=""

  # Read existing value if present
  if [ -f "$ENV_FILE" ]; then
    current=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- || true)
  fi

  echo ""
  echo -e "  ${BOLD}${var}${RESET}"
  echo -e "  ${DIM}${desc}${RESET}"
  [ -n "$example" ] && echo -e "  ${DIM}Example: ${example}${RESET}"
  if [ -n "$current" ]; then
    echo -e "  ${DIM}Current: ${current}${RESET}"
    read -r -p "  Value [leave blank to keep current]: " val
    val="${val:-$current}"
  else
    if [ "$required" = "no" ]; then
      read -r -p "  Value [optional, press Enter to skip]: " val
    else
      read -r -p "  Value: " val
      while [ -z "$val" ]; do
        warn "This field is required."
        read -r -p "  Value: " val
      done
    fi
  fi
  echo "$val"
}

if [ "${SKIP_ENV:-0}" = "0" ]; then
  echo -e "  ${DIM}Fill in your credentials. All values are written to ${ENV_FILE}${RESET}"
  echo -e "  ${DIM}Press Enter to keep an existing value.${RESET}"

  # ── GitHub
  divider
  echo -e "  ${BOLD}GitHub${RESET}"
  GITHUB_TOKEN=$(prompt_var "GITHUB_TOKEN" \
    "Personal Access Token with 'repo' (read) + 'read:org' scopes" \
    "ghp_xxxxxxxxxxxxxxxxxxxx")
  GITHUB_ORG=$(prompt_var "GITHUB_ORG" \
    "GitHub organisation slug" \
    "my-company")
  GITHUB_TEAM=$(prompt_var "GITHUB_TEAM" \
    "Team slug for PR review queue" \
    "platform-engineering")

  # ── Datadog
  divider
  echo -e "  ${BOLD}Datadog${RESET}"
  DD_API_KEY=$(prompt_var "DD_API_KEY" \
    "Datadog API key — from Organization Settings > API Keys" \
    "abc123...")
  DD_APP_KEY=$(prompt_var "DD_APP_KEY" \
    "Datadog Application key — from Organization Settings > Application Keys" \
    "def456...")
  DD_SITE=$(prompt_var "DD_SITE" \
    "Datadog API host (US1 default; change for EU/US3)" \
    "https://api.datadoghq.com" "no")
  DD_SITE="${DD_SITE:-https://api.datadoghq.com}"
  DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY=$(prompt_var "DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY" \
    "Full URL of your Catalogue Quality dashboard (copy from browser)" \
    "https://app.datadoghq.com/dashboard/abc-123/my-dashboard")
  DATADOG_DASHBOARD_URL_OWNER_METRICS=$(prompt_var "DATADOG_DASHBOARD_URL_OWNER_METRICS" \
    "Full URL of your Owner Metrics dashboard (copy from browser)" \
    "https://app.datadoghq.com/dashboard/xyz-456/owner-metrics")
  DATADOG_TEAMS=$(prompt_var "DATADOG_TEAMS" \
    "Comma-separated team slugs — filters all Datadog queries" \
    "team-a  or  team-a,team-b")

  # ── Gmail SMTP
  divider
  echo -e "  ${BOLD}Gmail SMTP${RESET}"
  echo -e "  ${DIM}Need an App Password? Go to: https://myaccount.google.com/apppasswords${RESET}"
  SMTP_USER=$(prompt_var "SMTP_USER" \
    "Your Gmail address" \
    "you@gmail.com")
  SMTP_PASSWORD=$(prompt_var "SMTP_PASSWORD" \
    "Gmail App Password (16 chars, spaces are fine)" \
    "xxxx xxxx xxxx xxxx")
  SMTP_FROM=$(prompt_var "SMTP_FROM" \
    "Sender address (usually same as SMTP_USER)" \
    "you@gmail.com")
  SMTP_TO=$(prompt_var "SMTP_TO" \
    "Recipient address for the daily report" \
    "you@work.com")

  # ── Todoist (optional)
  divider
  echo -e "  ${BOLD}Todoist${RESET} ${DIM}(optional — for todo list & reading queue)${RESET}"
  echo -e "  ${DIM}Get your token: Todoist > Settings > Integrations > Developer${RESET}"
  TODOIST_API_TOKEN=$(prompt_var "TODOIST_API_TOKEN" \
    "Todoist API token" \
    "0123456789abcdef..." "no")

  # Write .env (line-by-line — avoids a stray "EOF" line in a secret closing <<EOF early)
  {
    echo "# Generated by install.sh — $(date)"
    echo "# Re-run install.sh to update, or edit this file directly."
    echo ""
    echo "# ── GitHub ────────────────────────────────────────────────────────────────────"
    printf 'GITHUB_TOKEN=%s\n' "$GITHUB_TOKEN"
    printf 'GITHUB_ORG=%s\n' "$GITHUB_ORG"
    printf 'GITHUB_TEAM=%s\n' "$GITHUB_TEAM"
    echo ""
    echo "# ── Datadog ───────────────────────────────────────────────────────────────────"
    printf 'DD_API_KEY=%s\n' "$DD_API_KEY"
    printf 'DD_APP_KEY=%s\n' "$DD_APP_KEY"
    printf 'DD_SITE=%s\n' "$DD_SITE"
    printf 'DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY=%s\n' "$DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY"
    printf 'DATADOG_DASHBOARD_URL_OWNER_METRICS=%s\n' "$DATADOG_DASHBOARD_URL_OWNER_METRICS"
    printf 'DATADOG_TEAMS=%s\n' "$DATADOG_TEAMS"
    echo ""
    echo "# ── Email (Gmail SMTP) ────────────────────────────────────────────────────────"
    printf 'SMTP_USER=%s\n' "$SMTP_USER"
    printf 'SMTP_PASSWORD=%s\n' "$SMTP_PASSWORD"
    printf 'SMTP_FROM=%s\n' "$SMTP_FROM"
    printf 'SMTP_TO=%s\n' "$SMTP_TO"
    echo ""
    echo "# ── Todoist (todo list + reading queue) ──────────────────────────────────────"
    printf 'TODOIST_API_TOKEN=%s\n' "$TODOIST_API_TOKEN"
    echo "# TODOIST_PROJECT_ID is auto-populated by: python scripts/todo.py setup"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"   # secrets: owner-read-only
  success ".env written to $ENV_FILE"
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
divider
echo ""
