"""Smoke tests for the dockhand_discord_control package."""

import dockhand_discord_control


def test_package_exports_version() -> None:
    """The package should expose its version."""
    assert dockhand_discord_control.__version__ == "0.1.0"
