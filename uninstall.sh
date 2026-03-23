#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# second-brain — uninstaller
#
# Usage:
#   bash ~/.second-brain/uninstall.sh
# ────────────────────────────────────────────────────────────────────────────
set -euo pipefail

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
divider() { echo -e "${DIM}────────────────────────────────────────────────────${RESET}"; }

INSTALL_DIR="${INSTALL_DIR:-$HOME/.second-brain}"
BIN_DIR="${BIN_DIR:-$HOME/bin}"
RUNNER_SCRIPT="$BIN_DIR/run-daily-dashboard.sh"
PLIST_LABEL="com.$(whoami).daily-dashboard"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

echo ""
echo -e "${BOLD}  EM Second Brain — Uninstaller${RESET}"
divider
echo ""
warn "This will remove:"
echo -e "  ${DIM}  • LaunchAgent  $PLIST_PATH${RESET}"
echo -e "  ${DIM}  • Runner       $RUNNER_SCRIPT${RESET}"
echo -e "  ${DIM}  • Install dir  $INSTALL_DIR${RESET}"
echo ""
read -r -p "  Proceed? [y/N] " CONFIRM
echo ""
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "  Aborted."
  exit 0
fi

# 1. Unload and remove LaunchAgent
if [ -f "$PLIST_PATH" ]; then
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  rm -f "$PLIST_PATH"
  success "LaunchAgent removed"
else
  info "LaunchAgent not found — skipping"
fi

# 2. Remove runner script
if [ -f "$RUNNER_SCRIPT" ]; then
  rm -f "$RUNNER_SCRIPT"
  success "Runner script removed"
else
  info "Runner script not found — skipping"
fi

# 3. Remove install directory
if [ -d "$INSTALL_DIR" ]; then
  rm -rf "$INSTALL_DIR"
  success "Install directory removed: $INSTALL_DIR"
else
  info "Install directory not found — skipping"
fi

echo ""
divider
echo -e "  ${GREEN}${BOLD}Uninstall complete.${RESET}"
echo ""
