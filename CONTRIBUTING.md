# Contributing

Thanks for helping improve Engineering Pulse.

## Prerequisites

- Python 3.11 or newer
- `git`

## Local setup

```bash
git clone https://github.com/seek-oss/engineering-pulse.git
cd engineering-pulse
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Lint

```bash
ruff check scripts tests
ruff format --check scripts tests
```

Auto-fix where possible: `ruff check scripts tests --fix` and `ruff format scripts tests`.

## Run tests

Tests use mocked API credentials (see `tests/conftest.py`). No `.env` file is required.

```bash
python -m pytest tests/ --cov=scripts --cov-report=term-missing -q
```

This matches what [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs in CI (lint + Python 3.11 and 3.12). CI runs on every **push** to any branch and on **pull requests** targeting `main`.

## Pull requests

- Open a PR against `main`.
- Ensure CI passes (lint + both test matrix jobs).
- Do not commit secrets (`.env`, API keys, SMTP passwords).
- Keep local-only files out of the PR:
  - `prompts/dashboards/*.md` (except `_example.md`)
  - `prompts/extras/*.md` (except `_example.md`)
  - `prompts/stakeholders/*.md` (except `_example.md`)
  - `output/`

## Questions

Open a [GitHub issue](https://github.com/seek-oss/engineering-pulse/issues) for bugs or feature ideas.
