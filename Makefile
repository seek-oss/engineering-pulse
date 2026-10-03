# ────────────────────────────────────────────────────────────────────────────
# engineering-pulse — day-2 operations
# ────────────────────────────────────────────────────────────────────────────

INSTALL_DIR    ?= $(HOME)/.engineering-pulse
BIN_DIR        ?= $(HOME)/bin
RUNNER         := $(BIN_DIR)/run-daily-dashboard.sh
PLIST_LABEL    := com.$(shell whoami).daily-dashboard
PLIST_PATH     := $(HOME)/Library/LaunchAgents/$(PLIST_LABEL).plist
LOG_FILE       := /tmp/daily-dashboard.log
PYTHON         := $(INSTALL_DIR)/.venv/bin/python3

.DEFAULT_GOAL := help

# ── Help ─────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  engineering-pulse — available targets"
	@echo ""
	@echo "  make run          Run now (foreground: stream logs to terminal + /tmp/log)"
	@echo "  make run-bg       Run in background (log file only)"
	@echo "  make status       Show LaunchAgent status"
	@echo "  make logs         Tail the run log"
	@echo "  make logs-launchd Tail the launchd stdout/stderr"
	@echo "  make update       Pull latest code + reinstall dependencies"
	@echo "  make test         Run the test suite with coverage"
	@echo "  make reports      Open the report calendar in your browser"
	@echo "  make compare A=<id> B=<id>  Ask the agent to compare two archived reports"
	@echo "  make schedule-show Show the scheduled days and times"
	@echo "  make schedule     Reload the LaunchAgent (after plist changes)"
	@echo "  make unschedule   Unload the LaunchAgent (pause the schedule)"
	@echo "  make uninstall    Remove everything (LaunchAgent + files)"
	@echo "  make config       Open .env in your default editor"
	@echo ""

# ── Run ──────────────────────────────────────────────────────────────────────
.PHONY: run
run:
	@echo "→  Running daily dashboard (foreground → terminal + append $(LOG_FILE))…"
	@ENGINEERING_PULSE_RUN_FG=1 ENGINEERING_PULSE_MANUAL=1 "$(RUNNER)"

.PHONY: run-bg
run-bg:
	@echo "→  Running daily dashboard (background)…"
	@ENGINEERING_PULSE_MANUAL=1 "$(RUNNER)" &
	@echo "   Logs: tail -f $(LOG_FILE)"

# ── Logs ─────────────────────────────────────────────────────────────────────
.PHONY: logs
logs:
	@tail -f $(LOG_FILE)

.PHONY: logs-launchd
logs-launchd:
	@echo "─── stdout ───────────────────────────────────────"
	@tail -40 /tmp/daily-dashboard-launchd.out 2>/dev/null || echo "(empty)"
	@echo "─── stderr ───────────────────────────────────────"
	@tail -40 /tmp/daily-dashboard-launchd.err 2>/dev/null || echo "(empty)"

# ── LaunchAgent ──────────────────────────────────────────────────────────────
.PHONY: status
status:
	@echo "→  LaunchAgent status:"
	@launchctl list | grep "$(PLIST_LABEL)" || echo "  (not loaded)"
	@echo ""
	@echo "→  Plist: $(PLIST_PATH)"
	@ls -la "$(PLIST_PATH)" 2>/dev/null || echo "  (not found)"

.PHONY: schedule-show
schedule-show:
	@cd "$(INSTALL_DIR)" && $(PYTHON) scripts/schedule.py show

.PHONY: reports
reports:
	@cd "$(INSTALL_DIR)" && $(PYTHON) scripts/report_archive.py build-index
	@open "$(INSTALL_DIR)/output/reports/index.html"

.PHONY: compare
compare:
	@test -n "$(A)" -a -n "$(B)" || { echo "Usage: make compare A=<report-id> B=<report-id> (ids are on the calendar's Compare view)"; exit 2; }
	@echo "→  Comparing $(A) with $(B) (log: /tmp/engineering-pulse-compare.log)…"
	@bash "$(INSTALL_DIR)/scripts/run_compare.sh" "$(A)" "$(B)"

.PHONY: schedule
schedule:
	@launchctl unload "$(PLIST_PATH)" 2>/dev/null || true
	@launchctl load "$(PLIST_PATH)"
	@echo "✓  LaunchAgent reloaded: $(PLIST_LABEL)"

.PHONY: unschedule
unschedule:
	@launchctl unload "$(PLIST_PATH)" 2>/dev/null && echo "✓  LaunchAgent unloaded" || echo "  (was not loaded)"

# ── Update ───────────────────────────────────────────────────────────────────
.PHONY: update
update:
	@echo "→  Pulling latest code…"
	@git -C "$(INSTALL_DIR)" pull --ff-only
	@echo "→  Updating dependencies…"
	@$(INSTALL_DIR)/.venv/bin/pip install --quiet --upgrade pip
	@$(INSTALL_DIR)/.venv/bin/pip install --quiet -r "$(INSTALL_DIR)/requirements.txt"
	@echo "✓  Update complete"

# ── Test ─────────────────────────────────────────────────────────────────────
.PHONY: test
test:
	@cd "$(INSTALL_DIR)" && \
	  .venv/bin/python -m pytest tests/ --cov=scripts --cov-report=term-missing -q

# ── Config ───────────────────────────────────────────────────────────────────
.PHONY: config
config:
	@$${EDITOR:-nano} "$(INSTALL_DIR)/.env"

# ── Uninstall ────────────────────────────────────────────────────────────────
.PHONY: uninstall
uninstall:
	@bash "$(INSTALL_DIR)/uninstall.sh"
