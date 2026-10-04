#!/usr/bin/env bash
# run_compare.sh — run the report-compare skill through AGENT_CLI for two archived reports.
#
#   scripts/run_compare.sh <report-id-A> <report-id-B>
#   scripts/run_compare.sh --url 'engineering-pulse://compare?a=<id>&b=<id>'
#
# Called by `make compare` and by the "Engineering Pulse" link handler app that
# install.sh registers for engineering-pulse:// links on the report calendar.
# The ids are validated against the archive manifest before the agent runs.

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$HOME/bin"

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${COMPARE_LOG_FILE:-/tmp/engineering-pulse-compare.log}"
PY="$INSTALL_DIR/.venv/bin/python"
[[ -x "$PY" ]] || PY="python3"

# shellcheck source=scripts/lib/agent_cli.sh
source "$INSTALL_DIR/scripts/lib/agent_cli.sh"
load_agent_env "$INSTALL_DIR/.env"
cd "$INSTALL_DIR" || exit 1

log() { printf '%s\n' "[$(date)] $*" | tee -a "$LOG_FILE" >&2; }

fail() {
  log "Compare not started: $1"
  "$PY" scripts/notify_report.py --title "Comparison not started" --message "$1" \
    --open "$INSTALL_DIR/output/reports/index.html" >>"$LOG_FILE" 2>&1 || true
  exit 2
}

if [[ "${1:-}" == "--url" ]]; then
  ids=$("$PY" scripts/compare_reports.py parse-url "${2:-}" 2>>"$LOG_FILE") || fail "Unsupported link."
  read -r A B <<<"$ids"
else
  A="${1:-}"
  B="${2:-}"
fi
[[ -n "$A" && -n "$B" ]] || fail "Usage: run_compare.sh <report-id-A> <report-id-B>"

context=$("$PY" scripts/compare_reports.py prepare --a "$A" --b "$B" 2>>"$LOG_FILE") \
  || fail "$(tail -1 "$LOG_FILE" | sed 's/^Cannot compare: //')"

output_html=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["output_html"])' "$context")
subject=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["subject"])' "$context")

PROMPT="$(cat "$INSTALL_DIR/skills/report-compare/SKILL.md")

Context file for this run: $context"
AGENT=$(resolve_agent)

log "Starting compare $A vs $B (agent=$AGENT)"
start=$(date +%s)
"$PY" scripts/run_issues.py reset --type compare >>"$LOG_FILE" 2>&1 || true
if [[ -t 1 ]]; then
  run_agent "$AGENT" "$PROMPT" "$INSTALL_DIR" 2>&1 | tee -a "$LOG_FILE"
  ec=${PIPESTATUS[0]}
else
  run_agent "$AGENT" "$PROMPT" "$INSTALL_DIR" >>"$LOG_FILE" 2>&1
  ec=$?
fi
log "Compare finished — exit code $ec"

"$PY" scripts/deliver_report.py ensure --type compare --since "$start" --agent-exit "$ec" \
  --subject "$subject" "$output_html" >>"$LOG_FILE" 2>&1
