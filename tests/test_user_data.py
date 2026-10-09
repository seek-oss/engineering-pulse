"""Durable user-data paths and legacy migration."""

from __future__ import annotations

import json
import stat

from scripts import user_data


def test_default_paths_live_outside_checkout(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(user_data, "DEFAULT_DATA_DIR", home / ".engineering-pulse-data")
    monkeypatch.delenv(user_data.DATA_DIR_ENV, raising=False)

    assert user_data.data_dir() == home / ".engineering-pulse-data"
    assert user_data.dashboards_dir() == user_data.data_dir() / "dashboards"
    assert user_data.extras_dir() == user_data.data_dir() / "extras"
    assert user_data.reports_dir() == user_data.data_dir() / "reports"


def test_path_overrides(tmp_path, monkeypatch):
    data = tmp_path / "data"
    reports = tmp_path / "custom-reports"
    monkeypatch.setenv(user_data.DATA_DIR_ENV, str(data))
    monkeypatch.setenv("REPORTS_DIR", str(reports))

    assert user_data.data_dir() == data
    assert user_data.reports_dir() == reports


def test_data_dir_is_inferred_from_checkout_env_symlink(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    data = tmp_path / "custom-data"
    checkout.mkdir()
    data.mkdir()
    (data / ".env").write_text("DELIVERY=none\n")
    (checkout / ".env").symlink_to(data / ".env")
    monkeypatch.setattr(user_data, "ROOT", checkout)
    monkeypatch.delenv(user_data.DATA_DIR_ENV, raising=False)

    assert user_data.data_dir() == data
    assert user_data.env_file() == data / ".env"


def test_migrate_preserves_config_reports_and_custom_content(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    data = tmp_path / "durable"
    monkeypatch.setenv(user_data.DATA_DIR_ENV, str(data))
    monkeypatch.delenv("REPORTS_DIR", raising=False)

    (checkout / "prompts/dashboards").mkdir(parents=True)
    (checkout / "prompts/extras").mkdir(parents=True)
    (checkout / "output/reports/2026/10/01").mkdir(parents=True)
    (checkout / ".env.example").write_text("DELIVERY=notify\n")
    (checkout / ".env").write_text("DATADOG_TEAMS=talent\n")
    (checkout / "prompts/dashboards/_example.md").write_text("# template\n")
    (checkout / "prompts/dashboards/custom_team.md").write_text("# Team\n")
    (checkout / "prompts/extras/notes.md").write_text("# Notes\n")
    report = checkout / "output/reports/2026/10/01/pulse-090000.html"
    report.write_text("<h1>Report</h1>")
    entry = {
        "id": "pulse-20261001-090000",
        "timestamp": "2026-10-01T09:00:00+11:00",
        "path": "2026/10/01/pulse-090000.html",
    }
    (checkout / "output/reports/manifest.json").write_text(json.dumps({"entries": [entry]}))

    messages = user_data.migrate(checkout)

    assert messages
    assert (data / ".env").read_text() == "DATADOG_TEAMS=talent\n"
    assert stat.S_IMODE((data / ".env").stat().st_mode) == 0o600
    assert (checkout / ".env").is_symlink()
    assert (checkout / ".env").resolve() == data / ".env"
    assert (data / "dashboards/custom_team.md").is_file()
    assert not (data / "dashboards/_example.md").exists()
    assert (data / "extras/notes.md").is_file()
    assert (data / "reports/2026/10/01/pulse-090000.html").is_file()
    assert user_data._load_entries(data / "reports/manifest.json") == [entry]

    # Re-running migration is safe and does not duplicate manifest entries.
    user_data.migrate(checkout)
    assert user_data._load_entries(data / "reports/manifest.json") == [entry]


def test_existing_durable_env_wins_and_legacy_is_backed_up(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    data = tmp_path / "durable"
    monkeypatch.setenv(user_data.DATA_DIR_ENV, str(data))
    (checkout / "prompts/dashboards").mkdir(parents=True)
    (checkout / "prompts/extras").mkdir(parents=True)
    (checkout / ".env.example").write_text("EXAMPLE=1\n")
    (checkout / ".env").write_text("LEGACY=1\n")
    data.mkdir()
    (data / ".env").write_text("DURABLE=1\n")

    user_data.migrate(checkout)

    assert (data / ".env").read_text() == "DURABLE=1\n"
    assert list(data.glob(".env.legacy-*"))
    assert (checkout / ".env").resolve() == data / ".env"


def test_report_merge_renames_a_conflicting_path(tmp_path):
    src, dst = tmp_path / "legacy", tmp_path / "durable"
    rel = "2026/10/01/pulse-090000.html"
    for root, report_id, body in (
        (src, "pulse-20261001-090000", "legacy"),
        (dst, "pulse-20261001-090000-2", "durable"),
    ):
        (root / rel).parent.mkdir(parents=True)
        (root / rel).write_text(body)
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "id": report_id,
                            "timestamp": "2026-10-01T09:00:00+11:00",
                            "path": rel,
                        }
                    ]
                }
            )
        )

    assert user_data._merge_report_archive(src, dst) == 1
    entries = {entry["id"]: entry for entry in user_data._load_entries(dst / "manifest.json")}
    migrated = entries["pulse-20261001-090000"]
    assert (dst / migrated["path"]).read_text() == "legacy"
    assert (dst / rel).read_text() == "durable"
