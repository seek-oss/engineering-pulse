#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# engineering-pulse — installer
#
# One-liner (safe): bootstrap clones the repo, then runs this file from disk —
#   curl -fsSL https://raw.githubusercontent.com/seek-oss/engineering-pulse/main/web-install.sh | bash
#
# Or save then run (also safe):
#   curl -fsSL https://raw.githubusercontent.com/seek-oss/engineering-pulse/main/install.sh -o /tmp/ep-install.sh && bash /tmp/ep-install.sh
#
# Do NOT pipe this script into bash: stdin is the pipe, not your keyboard; a cached
# older copy on raw.githubusercontent.com can disagree with the repo you just cloned.
#
# Local / already cloned:
#   bash install.sh
# ────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/agent_cli.sh
source "$SCRIPT_DIR/scripts/lib/agent_cli.sh"

SELECTED_AGENT=""

# ── Colours ──────────────────────────────────────────────────────────────────
# Use ANSI-C quoting so codes are real ESC bytes (echo -e and read prompts work).
BOLD=$'\033[1m'
DIM=$'\033[2m'
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
CYAN=$'\033[0;36m'
RESET=$'\033[0m'

info()    { echo -e "  ${CYAN}→${RESET}  $*"; }
success() { echo -e "  ${GREEN}✓${RESET}  $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "  ${RED}✗${RESET}  $*" >&2; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }
divider() { echo -e "${DIM}────────────────────────────────────────────────────${RESET}"; }

# Vivid “what to do next” (works when stdin is a pipe — e.g. curl | bash)
MAGENTA=$'\033[0;35m'
post_install_guide() {
  local ex="$INSTALL_DIR/.env.example"
  echo ""
  echo -e "${BOLD}Next steps${RESET}"
  echo ""
  echo -e "  ${BOLD}1) Credentials & API keys${RESET} ${CYAN}(required)${RESET}"
  echo -e "     Edit: ${MAGENTA}${BOLD}${ENV_FILE}${RESET}"
  if [ -f "$ex" ]; then
    echo -e "     ${DIM}Template with every variable explained:${RESET} ${MAGENTA}${ex}${RESET}"
  fi
  echo -e "     ${DIM}GitHub PAT, Datadog API keys, SMTP, optional Todoist — see comments in .env.example.${RESET}"
  echo ""
  echo -e "  ${BOLD}2) Agent CLI (required)${RESET}"
  if [[ -n "${SELECTED_AGENT:-}" ]]; then
    echo -e "     Selected: ${CYAN}${BOLD}${SELECTED_AGENT}${RESET} ($(agent_label "$SELECTED_AGENT"))"
  fi
  echo -e "     Change:   edit ${BOLD}AGENT_CLI${RESET} in .env (options: claude, cursor, pi)"
  echo -e "     Skill the scheduler runs: ${MAGENTA}${BOLD}${INSTALL_DIR}/skills/engineering-pulse/SKILL.md${RESET}"
  echo -e "     ${DIM}In Cursor chat: ${RESET}${CYAN}${BOLD}/daily-dashboard${RESET}"
  echo -e "     ${DIM}Shipped dashboards live in: ${RESET}${MAGENTA}${INSTALL_DIR}/prompts/dashboards/${RESET}"
  echo ""
  echo -e "  ${BOLD}3) Add your own Datadog dashboards${RESET}"
  echo -e "     In Cursor, run: ${CYAN}${BOLD}/add-dashboard${RESET} ${DIM}and describe the dashboard${RESET}"
  echo -e "     ${DIM}This creates a file in prompts/dashboards/custom_*.md — safe to upgrade later.${RESET}"
  echo ""
  echo -e "  ${BOLD}4) Upgrading${RESET}"
  echo -e "     Re-run this installer or ${CYAN}git pull --ff-only${RESET} — your custom dashboards"
  echo -e "     ${DIM}(prompts/dashboards/custom_*.md) and .env are never overwritten.${RESET}"
  echo ""
  echo -e "  ${BOLD}5) Schedule (LaunchAgent)${RESET}"
  echo -e "     ${DIM}Installed plist:${RESET} ${MAGENTA}${BOLD}${PLIST_PATH}${RESET}"
  echo -e "     ${DIM}Default run times come from${RESET} ${BOLD}SCHEDULE_HOURS${RESET}${DIM} (${SCHEDULE_HOURS}) when you run this installer.${RESET}"
  echo -e "     ${DIM}To change times: edit the plist (duplicate${RESET} ${BOLD}StartCalendarInterval${RESET} ${DIM}dicts), then:${RESET}"
  echo -e "       ${CYAN}launchctl unload \"${PLIST_PATH}\" && launchctl load \"${PLIST_PATH}\"${RESET}"
  echo -e "     ${DIM}Or re-run this installer from a clone with${RESET} ${BOLD}SCHEDULE_HOURS=\"9 12 17\" bash install.sh${RESET}"
  echo ""
  echo -e "  ${BOLD}6) Run once after .env is filled${RESET}"
  echo -e "     ${CYAN}bash ${RUNNER_SCRIPT}${RESET}"
  echo -e "     ${DIM}Logs:${RESET} ${CYAN}tail -f ${LOG_FILE}${RESET} ${DIM}(cleared at run start if over 50 MiB)${RESET}"
  echo ""
  divider
}

# ── Config ───────────────────────────────────────────────────────────────────
REPO_URL="${REPO_URL:-https://github.com/seek-oss/engineering-pulse.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.engineering-pulse}"
BIN_DIR="${BIN_DIR:-$HOME/bin}"
RUNNER_SCRIPT="$BIN_DIR/run-daily-dashboard.sh"
PLIST_LABEL="com.$(whoami).daily-dashboard"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_FILE="/tmp/daily-dashboard.log"
SCHEDULE_HOURS="${SCHEDULE_HOURS:-9 12 16}"  # space-separated

use_color() {
  [[ -z "${NO_COLOR:-}" ]] && [[ -t 1 ]]
}

upsert_env_var() {
  local key="$1" val="$2" file="$3"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    if [[ "$(uname)" == Darwin ]]; then
      sed -i '' "s/^${key}=.*/${key}=${val}/" "$file"
    else
      sed -i "s/^${key}=.*/${key}=${val}/" "$file"
    fi
  else
    printf '\n%s=%s\n' "$key" "$val" >>"$file"
  fi
}

ensure_bin_in_path() {
  local zshrc="$HOME/.zshrc"
  local line='export PATH="$HOME/bin:$PATH"'
  if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
    return 0
  fi
  touch "$zshrc"
  if grep -Fq 'HOME/bin' "$zshrc" 2>/dev/null; then
    return 0
  fi
  echo "$line" >>"$zshrc"
  success "Added ~/bin to PATH in ~/.zshrc"
}

# Bash 3.2-compatible: macOS ships bash without `declare -A` (associative arrays).
_detected_has_agent() {
  local needle="$1"
  local haystack="$2"
  local w
  for w in $haystack; do
    [[ "$w" == "$needle" ]] && return 0
  done
  return 1
}

show_agent_selector() {
  # NOTE: This function is often called as $(show_agent_selector ...). Command
  # substitution only shows stderr to the user — everything except the final
  # agent id must go to >&2.
  local default="$1"
  local detected="$2"

  divider >&2
  echo "" >&2
  echo -e "  ${CYAN}→${RESET}  ${BOLD}Pick the AI tool for scheduled runs${RESET} (saved as ${BOLD}AGENT_CLI${RESET} in .env)." >&2
  echo "" >&2
  echo -e "${BOLD}────────────── Choose your AI agent: ──────────────${RESET}" >&2
  echo "" >&2

  if [[ -z "$detected" ]]; then
    warn "None detected. We recommend Claude Code:" >&2
    warn "  $(agent_install_hint claude)" >&2
    echo "" >&2
  fi

  local -a menu_labels=()
  local idx=1
  local default_idx=1
  for a in "${AGENT_ORDER[@]}"; do
    local status="(not found)"
    if _detected_has_agent "$a" "$detected"; then
      status="(detected)"
    fi
    local rec=""
    [[ "$a" == "$default" ]] && rec=" ✦ recommended"
    menu_labels+=("${a}: $(agent_label "$a")  ${status}${rec}")
    [[ "$a" == "$default" ]] && default_idx=$idx
    idx=$((idx + 1))
  done

  if command -v gum &>/dev/null && [[ -t 0 ]]; then
    local choice
    choice=$(
      gum choose "${menu_labels[@]}" \
        --selected "${menu_labels[$((default_idx - 1))]}" \
        --height 5 2>/dev/null || true
    )
    if [[ -n "$choice" ]]; then
      echo "${choice%%:*}"
      return 0
    fi
  fi

  if command -v fzf &>/dev/null && [[ -t 0 ]]; then
    local choice
    choice=$(
      printf '%s\n' "${menu_labels[@]}" \
        | fzf --height=6 --reverse --prompt="Agent> " \
        --query="${menu_labels[$((default_idx - 1))]}" 2>/dev/null || true
    )
    if [[ -n "$choice" ]]; then
      echo "${choice%%:*}"
      return 0
    fi
  fi

  local i=1 opt
  for opt in "${menu_labels[@]}"; do
    echo "  $i) $opt" >&2
    i=$((i + 1))
  done
  echo "" >&2

  local default_pick_name=""
  default_pick_name=$(agent_label "${AGENT_ORDER[$((default_idx - 1))]}")

  echo "" >&2
  printf '  Type 1-3, or press Enter for default %s (%s).\n  › ' "$default_idx" "$default_pick_name" >&2

  local pick="$default_idx"
  if [[ -t 0 ]]; then
    read -r pick || true
    pick="${pick:-$default_idx}"
  fi
  if [[ "$pick" =~ ^[1-3]$ ]]; then
    echo "${AGENT_ORDER[$((pick - 1))]}"
  else
    echo "$default"
  fi
}

print_banner() {
  local use_color=true
  if [[ -n "${NO_COLOR:-}" ]] || [[ ! -t 1 ]]; then
    use_color=false
  fi
 
  local C1="" C2="" C3="" C4="" C5="" CG="" CR=""
  if $use_color; then
    C1=$'\033[1;36m'   # bright cyan
    C2=$'\033[0;36m'   # cyan
    C3=$'\033[1;32m'   # bright green
    C4=$'\033[0;32m'   # green
    C5=$'\033[1;37m'   # bright white
    CG=$'\033[0;32m'   # green (for frame)
    CR=$'\033[0m'      # reset
  fi
 
  printf '\n'
  printf '%s+ ------------------------------------------------------------------- +%s\n' "$CG" "$CR"
  printf '%s|           >  E N G I N E E R I N G   P U L S E  <                  |%s\n' "$CG" "$CR"
  printf '%s|             real-time pulse for systems that matter                  |%s\n' "$CG" "$CR"
  printf '%s+ ------------------------------------------------------------------- +%s\n' "$CG" "$CR"
  printf '\n'
 
  # Block letter "PULSE" with cyan → green → white gradient
  printf '%s     ████████  ██    ██  ██         ██████   ████████%s\n' "$C1" "$CR"
  printf '%s     ██    ██  ██    ██  ██        ██        ██      %s\n' "$C1" "$CR"
  printf '%s     ██    ██  ██    ██  ██        ██        ██      %s\n' "$C2" "$CR"
  printf '%s     ████████  ██    ██  ██         ██████   ██████  %s\n' "$C3" "$CR"
  printf '%s     ██        ██    ██  ██              ██  ██      %s\n' "$C4" "$CR"
  printf '%s     ██        ██    ██  ██              ██  ██      %s\n' "$C4" "$CR"
  printf '%s     ██         ██████   ████████   ██████   ████████%s\n' "$C5" "$CR"
 
  printf '\n'
  printf '%s           d a t a d o g  ·  g i t h u b  ·  e m a i l%s\n' "$CG" "$CR"
  printf '\n'
  printf '%s+ -------------------------------------- +%s\n' "$CG" "$CR"
  printf '%s| [✓] engine      : online               |%s\n' "$CG" "$CR"
  printf '%s| [✓] pulse       : steady               |%s\n' "$CG" "$CR"
  printf '%s| [✓] signal      : strong               |%s\n' "$CG" "$CR"
  printf '%s| [✓] status      : installing           |%s\n' "$CG" "$CR"
  printf '%s+ -------------------------------------- +%s\n' "$CG" "$CR"
  printf '\n'
  printf '%s=====================================================================%s\n' "$CG" "$CR"
  printf '%s         Keep building. Keep pushing. The pulse is alive.%s\n' "$C5" "$CR"
  printf '%s=====================================================================%s\n' "$CG" "$CR"
  printf '\n'
}

# ── Banner ───────────────────────────────────────────────────────────────────
print_banner

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

DETECTED_AGENTS=$(detect_agents)
if [[ -n "$DETECTED_AGENTS" ]]; then
  success "Agent CLI(s) detected: $DETECTED_AGENTS"
else
  warn "No agent CLI detected (install Claude Code, Cursor CLI, or Pi Agent)"
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

# Re-source lib from install dir (updated on clone/pull)
# shellcheck source=scripts/lib/agent_cli.sh
source "$INSTALL_DIR/scripts/lib/agent_cli.sh"

DEFAULT_AGENT=$(default_agent_choice "$DETECTED_AGENTS")
if [[ -t 0 ]]; then
  SELECTED_AGENT=$(show_agent_selector "$DEFAULT_AGENT" "$DETECTED_AGENTS")
  upsert_env_var "AGENT_CLI" "$SELECTED_AGENT" "$ENV_FILE"
  success "Selected agent: $(agent_label "$SELECTED_AGENT") (AGENT_CLI=$SELECTED_AGENT)"
  if ! agent_is_installed "$SELECTED_AGENT"; then
    warn "$(agent_label "$SELECTED_AGENT") is not installed yet. Install it:"
    warn "  $(agent_install_hint "$SELECTED_AGENT")"
    warn "The schedule will not work until the agent CLI is available."
  fi
else
  if ! grep -q '^AGENT_CLI=' "$ENV_FILE" 2>/dev/null; then
    SELECTED_AGENT="$DEFAULT_AGENT"
    upsert_env_var "AGENT_CLI" "$SELECTED_AGENT" "$ENV_FILE"
    info "Non-interactive install: set AGENT_CLI=$SELECTED_AGENT (edit .env to change)"
  else
    SELECTED_AGENT=$(grep '^AGENT_CLI=' "$ENV_FILE" | head -1 | cut -d= -f2-)
    info "Keeping existing AGENT_CLI=$SELECTED_AGENT"
  fi
fi

# ── 4. Shell runner script ────────────────────────────────────────────────────
header "4/5  Installing runner script"

mkdir -p "$BIN_DIR"
# Shell-quote paths here; the heredoc only expands $qi / $ql so runner lines are not
# executed by the parent shell if delimiter parsing ever goes wrong.
qi=$(printf '%q' "$INSTALL_DIR")
ql=$(printf '%q' "$LOG_FILE")
qal=$(printf '%q' "$INSTALL_DIR/scripts/lib/agent_cli.sh")
cat > "$RUNNER_SCRIPT" <<EOF
#!/usr/bin/env zsh
# run-daily-dashboard.sh — generated by engineering-pulse install.sh
# Invokes AGENT_CLI per skills/engineering-pulse/SKILL.md.
# Makefile sets ENGINEERING_PULSE_RUN_FG=1 so output is tee'd to tty + \$LOG_FILE; LaunchAgent omits it.

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$HOME/.local/bin:\$HOME/bin"

INSTALL_DIR=$qi
LOG_FILE=$ql
AGENT_LIB=$qal

# shellcheck source=scripts/lib/agent_cli.sh
source "\$AGENT_LIB"
load_agent_env "\$INSTALL_DIR/.env"

# Cap run log: clear if over 50 MiB (hardcoded; avoids unbounded growth).
if [[ -f "\$LOG_FILE" ]]; then
  sz=\$(wc -c <"\$LOG_FILE" | tr -d ' ')
  maxb=\$(( 50 * 1024 * 1024 ))
  if (( sz > maxb )); then
    print -r "[\$(date)] Log cleared: previous size was \${sz} bytes (> 50 MiB)" >"\$LOG_FILE"
  fi
fi

cd "\$INSTALL_DIR" || exit 1
source "\$INSTALL_DIR/.venv/bin/activate"

PROMPT=\$(cat "\$INSTALL_DIR/skills/engineering-pulse/SKILL.md")
AGENT=\$(resolve_agent)

setopt PIPE_FAIL 2>/dev/null || set -o pipefail

if [[ -n \${ENGINEERING_PULSE_RUN_FG:-} ]]; then
  print -r -- "[\$(date)] Starting daily-dashboard run (agent=\$AGENT)" | tee -a "\$LOG_FILE"
  run_agent "\$AGENT" "\$PROMPT" "\$INSTALL_DIR" 2>&1 | tee -a "\$LOG_FILE"
  _ec=\$?
  print -r -- "[\$(date)] Finished — exit code \$_ec" | tee -a "\$LOG_FILE"
else
  print -r -- "[\$(date)] Starting daily-dashboard run (agent=\$AGENT)" >> "\$LOG_FILE"
  if ! run_agent "\$AGENT" "\$PROMPT" "\$INSTALL_DIR" >>"\$LOG_FILE" 2>&1; then
    _ec=\$?
    print -r -- "[\$(date)] Finished — exit code \$_ec" >> "\$LOG_FILE"
    exit \$_ec
  fi
  _ec=\$?
  print -r -- "[\$(date)] Finished — exit code \$_ec" >> "\$LOG_FILE"
fi
exit \$_ec
EOF
chmod +x "$RUNNER_SCRIPT"
success "Runner script written to $RUNNER_SCRIPT"

# Optional interactive-shell convenience hint. The LaunchAgent and quick-reference
# commands use RUNNER_SCRIPT by absolute path, so PATH is only needed for invoking
# run-daily-dashboard.sh directly by name.
ensure_bin_in_path

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
  # Weekday 1=Mon … 5=Fri (macOS launchd convention)
  INTERVAL_ENTRIES=""
  for H in $SCHEDULE_HOURS; do
    for DAY in 1 2 3 4 5; do
      INTERVAL_ENTRIES+="
      <dict>
        <key>Weekday</key>
        <integer>${DAY}</integer>
        <key>Hour</key>
        <integer>${H}</integer>
        <key>Minute</key>
        <integer>0</integer>
      </dict>"
    done
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
  info "Schedule: runs at $(echo "$SCHEDULE_HOURS" | sed 's/ /:00, /g'):00 Mon–Fri"
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
