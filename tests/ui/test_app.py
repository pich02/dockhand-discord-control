"""Tests for the Reflex application wiring."""

from __future__ import annotations

import reflex as rx

from dockhand_discord_control.ui import app as app_module
from dockhand_discord_control.ui.app import _start_discord_bridge, build_app


def test_build_app_returns_configured_app(tmp_path, monkeypatch) -> None:
    # Isolate the working directory so the bridge's SQLite settings file is
    # not created inside the repository.
    monkeypatch.chdir(tmp_path)
    app = build_app()

    assert isinstance(app, rx.App)


def test_start_discord_bridge_closes_settings_repo(tmp_path, monkeypatch) -> None:
    closed = {"count": 0}

    class FakeSettings:
        def __init__(self) -> None:
            self.db_path = str(tmp_path / "app.sqlite")

    class FakeRepo:
        def __init__(self, db_path: str) -> None:
            self.db_path = db_path

        def get_dockhand_settings(self) -> tuple[str, str]:
            return "http://dockhand:8080", "dockhand-secret"

        def get_discord_token(self) -> str | None:
            return None

        def get_discord_guild_id(self) -> str | None:
            return None

        def close(self) -> None:
            closed["count"] += 1

    monkeypatch.setattr(app_module, "Settings", FakeSettings)
    monkeypatch.setattr(app_module, "SqliteSettingsRepository", FakeRepo)

    _start_discord_bridge()

    assert closed["count"] == 1
