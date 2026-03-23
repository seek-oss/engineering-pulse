#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# engineering-pulse — web bootstrap (safe for: curl … | bash)
#
# Clones or updates the repo, then runs install.sh from disk. The full installer
# must NOT be piped into bash: stdin would be the pipe, not your terminal, and
# raw.githubusercontent.com may cache an older install.sh than git clone fetches.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/harryzhu2011/engineering-pulse/main/web-install.sh | bash
#
# Optional env (same as install.sh):
#   REPO_URL  INSTALL_DIR  SCHEDULE_HOURS  BIN_DIR
# ────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/harryzhu2011/engineering-pulse.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.engineering-pulse}"

echo ""
echo "  Engineering Pulse — web bootstrap"
echo "  (clone/update repo, then run install.sh from disk)"
echo ""

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "  →  Updating $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "  →  Cloning into $INSTALL_DIR"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

exec bash "$INSTALL_DIR/install.sh"
