# ────────────────────────────────────────────────────────────────────────────
# second-brain — day-2 operations
# ────────────────────────────────────────────────────────────────────────────

INSTALL_DIR    ?= $(HOME)/.second-brain
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
	@echo "  second-brain — available targets"
	@echo ""
	@echo "  make run          Run the dashboard right now (foreground)"
	@echo "  make run-bg       Run the dashboard in the background"
	@echo "  make status       Show LaunchAgent status"
	@echo "  make logs         Tail the run log"
	@echo "  make logs-launchd Tail the launchd stdout/stderr"
	@echo "  make update       Pull latest code + reinstall dependencies"
	@echo "  make test         Run the test suite with coverage"
	@echo "  make schedule     Reload the LaunchAgent (after plist changes)"
	@echo "  make unschedule   Unload the LaunchAgent (pause the schedule)"
	@echo "  make uninstall    Remove everything (LaunchAgent + files)"
	@echo "  make config       Open .env in your default editor"
	@echo ""

# ── Run ──────────────────────────────────────────────────────────────────────
.PHONY: run
run:
	@echo "→  Running daily dashboard (foreground)…"
	@bash $(RUNNER)

.PHONY: run-bg
run-bg:
	@echo "→  Running daily dashboard (background)…"
	@bash $(RUNNER) &
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
