<!--
Sync Impact Report
- Version change: template placeholders → 1.0.0
- Modified principles: all five filled (Agent-and-Skill-First, Thin Scripts,
  Portable Skill/Multi-Harness, Secrets Hygiene, Quality Gates)
- Added sections: Additional Constraints — Technology & Architecture;
  Development Workflow
- Removed sections: none (template placeholders replaced)
- Templates: plan-template.md ✅ updated; tasks-template.md ✅ updated;
  spec-template.md ✅ no change required; .cursor/rules/specify-rules.mdc ✅ updated
- Follow-up TODOs: none
-->

# Engineering Pulse Constitution

## Core Principles

### I. Agent-and-Skill-First Product Runtime (NON-NEGOTIABLE)

The canonical daily-dashboard workflow MUST live in
`skills/engineering-pulse/SKILL.md` plus `skills/engineering-pulse/references/`.
`make run`, LaunchAgent, and `~/bin/run-daily-dashboard.sh` MUST stay agent-driven
through `AGENT_CLI` (`scripts/lib/agent_cli.sh`) — `claude`, `cursor`, or `pi`
(experimental). The primary product path MUST NOT be replaced by a direct
Python-only orchestration pipeline. `scripts/run_daily_dashboard.py` is a
helper/debug path only, not the scheduled runtime. Headless agent runs MUST use
explicit non-interactive permission handling (trust/force or equivalent) so
automation never blocks on an approval UI.

**Rationale:** The product is the skill-driven workflow, not a batch script.

### II. Thin Deterministic Script Layer

`scripts/*.py` MUST remain thin orchestration: fetch, transform, render, and
send with clear CLI boundaries and JSON/HTML artifacts under `output/`. Workflow
decisions, step-ordering prose, and agent instructions MUST stay in skill
references — not duplicated inside Python except for mechanical I/O. New
integrations MUST expose script CLIs callable from the skill; avoid embedding
business workflow logic in scripts. Terminal output MUST use `rich`; colour
semantics: red = attention, yellow = watch, green = healthy.

**Rationale:** Scripts are reliable tools; the agent applies judgment (e.g.
Stakeholder Pulse via Glean MCP).

### III. Portable Agent Skill and Multi-Harness

The publishable skill lives under `skills/engineering-pulse/` per the
[Agent Skills](https://agentskills.io/specification) spec. Harness adapters live
under `harness/` and `.cursor/skills/` (symlinks/adapters only — do not fork
workflow prose per IDE). Features MUST NOT hard-code a single agent vendor;
keep `AGENT_CLI` abstraction and harness docs in sync. User workspace data
(`prompts/dashboards/`, `prompts/extras/`) is separate from workflow code;
dashboard and extras files are gitignored except `_example.md` templates.

**Rationale:** One skill, many entrypoints (Cursor `/daily-dashboard`, Claude
Code, scheduled headless runs).

### IV. Secrets, Config, and User Data Hygiene (NON-NEGOTIABLE)

All credentials and org-specific config MUST come from `.env` via python-dotenv
only — never hardcode tokens, org URLs, team names, or real stakeholder PII in
tracked files. Use env vars (`DATADOG_TEAMS`, `GITHUB_ORG`, `GITHUB_TEAM`,
`STAKEHOLDERS`, `SMTP_*`, etc.); bundled demo or fixture data MUST use
fictional orgs and names only. Generated artifacts belong in `output/`
(gitignored): `*_metric_results.json`, `github_prs.json`, `todos.json`,
`stakeholders/*.md`, `daily_dashboard_report.html`. Pull requests MUST NOT
include `.env`, `output/`, or user dashboard/extras markdown.

**Rationale:** Safe OSS distribution and safe per-user installs
(`~/.engineering-pulse`).

### V. Quality Gates: Tested, Linted, Minimal Scope

Changes MUST pass `ruff check`/`ruff format` and `pytest` (tests use mocks —
no live API keys required in CI). CI (`.github/workflows/ci.yml`) MUST stay
green on push/PR; match `CONTRIBUTING.md`. Prefer the smallest correct diff;
avoid new dependencies unless justified. Behaviour changes MUST include or
update tests (see `tests/test_render_*`, `tests/conftest.py` patterns).

**Rationale:** Maintainable OSS with predictable releases.

## Additional Constraints — Technology & Architecture

- **Stack:** Python scripts, HTML scorecard renderer, SMTP email, optional MCP
  (Glean) for Stakeholder Pulse; Datadog, GitHub, and Todoist via REST/GraphQL
  APIs.
- **Plugin folders:** `prompts/dashboards/` (Datadog URL defs), `prompts/extras/`
  (drop-in markdown cards), `output/stakeholders/` (agent-generated Pulse cards).
- **HTML sections:** Part letters (A, B, C…) are dynamic — dashboards first, then
  PR queue, My Queue, Extras, Stakeholder Pulse when `STAKEHOLDERS` is set in
  `.env`.
- **Stakeholder Pulse:** One card per name in `STAKEHOLDERS` order; the renderer
  MUST show placeholders for missing cards rather than silently omitting names.
- **Installer:** `web-install.sh` → `install.sh`; default install path is
  `~/.engineering-pulse`; `git pull` upgrades scripts/skills but never user
  `.env` or gitignored prompts.

## Development Workflow

- `AGENTS.md` provides always-on agent context for Engineering Pulse development.
- `README.md` is the user-facing source of truth for what the project does and
  how to use it.
- `CONTRIBUTING.md` defines contribution and pull request expectations.
- Spec Kit artifacts live under `specs/<branch-id>/`; feature branches SHOULD use
  the `00N-feature-name` convention where practical.
- All Spec Kit feature work MUST follow the constitution through the
  spec → plan → tasks → implement flow.
- Each feature plan MUST include a **Constitution Check** that explains which
  principles apply and confirms there is no regression to:
  - read-only briefing behaviour (demo/fixture paths that do not mutate live
    systems or send email without explicit opt-in);
  - agent-driven scheduled/headless runs;
  - secrets hygiene;
  - privacy-safe demo and development workflows.
- Runtime guidance for agents SHOULD come from `AGENTS.md` and
  `skills/engineering-pulse/`. One-off prompts may refine a task, but MUST NOT
  contradict the constitution unless the constitution is amended.

## Governance

This constitution governs Engineering Pulse development decisions. If a feature
requires an exception, the exception MUST be justified in `plan.md` Complexity
Tracking. Amendments MUST update `CONSTITUTION_VERSION`, `LAST_AMENDED_DATE`,
and any affected `.specify/templates/*` files when mandatory sections change.
All pull requests and Spec Kit plans MUST verify compliance with principles
I–V before merge or implementation.

**Version**: 1.0.0 | **Ratified**: 2026-07-05 | **Last Amended**: 2026-07-05
