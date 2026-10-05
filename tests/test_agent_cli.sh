#!/usr/bin/env bash
# Shell tests for scripts/lib/agent_cli.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/agent_cli.sh
source "$ROOT/scripts/lib/agent_cli.sh"

failures=0
assert_eq() {
  local got="$1" expected="$2" msg="$3"
  if [[ "$got" != "$expected" ]]; then
    echo "FAIL: $msg (got '$got', expected '$expected')" >&2
    failures=$((failures + 1))
  fi
}

# resolve_agent respects AGENT_CLI env
AGENT_CLI=pi
assert_eq "$(resolve_agent)" "pi" "AGENT_CLI override"

unset AGENT_CLI
PATH="/usr/bin:/bin"
assert_eq "$(resolve_agent)" "cursor" "default when nothing detected"

# Cursor comes first in the installer menu, so it is the default when both are installed
MOCK_BIN="$(mktemp -d)"
printf '#!/bin/sh\nexit 0\n' >"$MOCK_BIN/agent"
printf '#!/bin/sh\nexit 0\n' >"$MOCK_BIN/claude"
chmod +x "$MOCK_BIN/agent" "$MOCK_BIN/claude"
PATH="$MOCK_BIN:/usr/bin:/bin"
assert_eq "$(detect_agents)" "cursor claude" "cursor listed first"
assert_eq "$(resolve_agent)" "cursor" "cursor default when both installed"
rm -rf "$MOCK_BIN"
PATH="/usr/bin:/bin"

# detect_agents with mocked PATH
MOCK_BIN="$(mktemp -d)"
printf '#!/bin/sh\nexit 0\n' >"$MOCK_BIN/agent"
chmod +x "$MOCK_BIN/agent"
PATH="$MOCK_BIN:$PATH"
detected=$(detect_agents)
assert_eq "$detected" "cursor" "detect cursor only"
rm -rf "$MOCK_BIN"

# Claude Code headless runs must not wait for permission prompts that cannot
# reach LaunchAgent / make-run users.
MOCK_BIN="$(mktemp -d)"
MOCK_LOG="$(mktemp)"
cat >"$MOCK_BIN/claude" <<'SH'
#!/bin/sh
printf '%s\n' "$*" >"$MOCK_LOG"
SH
chmod +x "$MOCK_BIN/claude"
PATH="$MOCK_BIN:/usr/bin:/bin"
export MOCK_LOG
run_agent claude "test prompt" "$ROOT"
assert_eq "$(cat "$MOCK_LOG")" "-p --permission-mode bypassPermissions -- test prompt" "claude bypasses headless permission prompts"
rm -rf "$MOCK_BIN"
rm -f "$MOCK_LOG"

if [[ "$failures" -gt 0 ]]; then
  echo "$failures test(s) failed" >&2
  exit 1
fi
echo "OK: agent_cli tests passed"
