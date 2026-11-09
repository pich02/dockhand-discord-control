"""Tests for the Reflex application wiring."""

from __future__ import annotations

import reflex as rx

from dockhand_discord_control.ui.app import build_app


def test_build_app_returns_configured_app(tmp_path, monkeypatch) -> None:
    # Isolate the working directory so the bridge's SQLite settings file is
    # not created inside the repository.
    monkeypatch.chdir(tmp_path)
    app = build_app()

    assert isinstance(app, rx.App)
