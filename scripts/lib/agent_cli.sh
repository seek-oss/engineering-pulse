#!/usr/bin/env bash
# Agent CLI abstraction for scheduled dashboard runs (Claude Code, Cursor, Pi).
# Sourced by install.sh and ~/bin/run-daily-dashboard.sh — do not execute directly.

AGENT_ORDER=(claude cursor pi)

agent_label() {
  case "$1" in
    claude) echo "Claude Code" ;;
    cursor) echo "Cursor CLI" ;;
    pi) echo "Pi Agent" ;;
    *) echo "$1" ;;
  esac
}

agent_install_hint() {
  case "$1" in
    claude) echo "npm install -g @anthropic-ai/claude-code" ;;
    cursor) echo "curl https://cursor.com/install -fsSL | bash" ;;
    pi) echo "curl -fsSL https://pi.dev/install.sh | sh" ;;
    *) echo "(unknown agent)" ;;
  esac
}

agent_cmd_for_id() {
  case "$1" in
    claude) echo "claude" ;;
    cursor) echo "agent" ;;
    pi) echo "pi" ;;
    *) return 1 ;;
  esac
}

agent_is_installed() {
  local cmd
  cmd=$(agent_cmd_for_id "$1") || return 1
  command -v "$cmd" &>/dev/null
}

detect_agents() {
  local found=()
  local a
  for a in "${AGENT_ORDER[@]}"; do
    if agent_is_installed "$a"; then
      found+=("$a")
    fi
  done
  if ((${#found[@]} > 0)); then
    echo "${found[@]}"
  fi
}

default_agent_choice() {
  local detected="$1"
  local a
  for a in ${detected:-}; do
    echo "$a"
    return 0
  done
  echo "claude"
}

load_agent_env() {
  local env_file="${1:-}"
  [[ -n "$env_file" && -f "$env_file" ]] || return 0
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      val="${BASH_REMATCH[2]}"
      val="${val%\"}"
      val="${val#\"}"
      val="${val%\'}"
      val="${val#\'}"
      export "$key=$val"
    fi
  done <"$env_file"
}

resolve_agent() {
  if [[ -n "${AGENT_CLI:-}" ]]; then
    echo "$AGENT_CLI"
    return 0
  fi
  local detected
  detected=$(detect_agents)
  default_agent_choice "$detected"
}

run_agent() {
  local agent="$1"
  local prompt="$2"
  local workdir="$3"

  if [[ -z "$agent" ]]; then
    echo "ERROR: No agent CLI configured." >&2
    echo "" >&2
    echo "Re-run the installer to choose an agent, or set AGENT_CLI in .env:" >&2
    echo "  claude — Claude Code  ($(agent_install_hint claude))" >&2
    echo "  cursor — Cursor CLI   ($(agent_install_hint cursor))" >&2
    echo "  pi     — Pi Agent     ($(agent_install_hint pi))" >&2
    return 1
  fi

  if ! agent_is_installed "$agent"; then
    echo "ERROR: $(agent_label "$agent") is not installed ($(agent_install_hint "$agent"))." >&2
    return 1
  fi

  case "$agent" in
    pi)
      (cd "$workdir" && pi -p --trust --force "$prompt")
      ;;
    claude)
      (cd "$workdir" && claude -p "$prompt")
      ;;
    cursor)
      (cd "$workdir" && agent -p --trust --force "$prompt")
      ;;
    *)
      echo "ERROR: Unknown AGENT_CLI='$agent' (expected: claude, cursor, pi)." >&2
      return 1
      ;;
  esac
}
