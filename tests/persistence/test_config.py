"""Tests for the Settings model."""

from __future__ import annotations

from dockhand_discord_control.persistence import Settings


def test_settings_defaults(monkeypatch) -> None:
    monkeypatch.delenv("DB_PATH", raising=False)
    settings = Settings()
    assert settings.db_path == "./data/app.sqlite"


def test_settings_reads_db_path_environment(monkeypatch) -> None:
    monkeypatch.setenv("DB_PATH", "/tmp/custom/app.sqlite")
    settings = Settings()
    assert settings.db_path == "/tmp/custom/app.sqlite"


def test_settings_has_no_legacy_secret_fields() -> None:
    settings = Settings()
    assert not hasattr(settings, "dockhand_base_url")
    assert not hasattr(settings, "dockhand_api_token")
    assert not hasattr(settings, "discord_bot_token")
    assert not hasattr(settings, "discord_guild_id")
