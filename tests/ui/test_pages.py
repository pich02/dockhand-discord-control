"""Tests for the Reflex page builders.

The pages are built but not rendered (no browser, no network).  These tests
only verify that each page function returns a Reflex component.
"""

from __future__ import annotations

import reflex as rx

from dockhand_discord_control.ui.pages import (
    dashboard_page,
    mappings_page,
    settings_page,
)


def test_dashboard_page_returns_component() -> None:
    assert isinstance(dashboard_page(), rx.Component)


def test_settings_page_returns_component() -> None:
    assert isinstance(settings_page(), rx.Component)


def test_mappings_page_returns_component() -> None:
    assert isinstance(mappings_page(), rx.Component)
