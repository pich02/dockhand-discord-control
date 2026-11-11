"""Reflex application wiring for the Dockhand Discord Control web UI.

:func:`build_app` creates the :class:`reflex.app.App`, registers the UI pages
and starts the Discord bridge as a best-effort background daemon thread.
"""

from __future__ import annotations

import logging

import reflex as rx

from dockhand_discord_control.persistence import Settings, SqliteSettingsRepository

from .bridge import discord_bridge
from .pages import dashboard_page, mappings_page, settings_page
from .state import AppState

logger = logging.getLogger(__name__)


def build_app() -> rx.App:
    """Create the Reflex app and start the Discord bridge (best-effort).

    The bridge is started in a background daemon thread so the UI keeps
    responding even if Discord cannot be reached.
    """
    app = rx.App(_state=AppState)
    app.add_page(
        dashboard_page,
        route="/",
        on_load=AppState.load_dashboard,  # type: ignore[arg-type]
    )
    app.add_page(
        settings_page,
        route="/settings",
        on_load=AppState.load_settings,  # type: ignore[arg-type]
    )
    app.add_page(
        mappings_page,
        route="/mappings",
        on_load=AppState.load_mappings_page,  # type: ignore[arg-type]
    )
    _start_discord_bridge()
    return app


def _start_discord_bridge() -> None:
    """Start the Discord bot in a background daemon thread, best-effort.

    Never raises: a missing token or any adapter failure is logged and the UI
    keeps running.  The bridge is the shared instance used by the settings
    page, so a token saved at runtime restarts the bot in place.
    """
    try:
        db_path = Settings().db_path
        settings_repo = SqliteSettingsRepository(db_path)
        base_url, api_token = settings_repo.get_dockhand_settings()
        token = settings_repo.get_discord_token()
        guild_id = settings_repo.get_discord_guild_id()
    except Exception as exc:  # pragma: no cover - infrastructure failure
        logger.warning("Discord bridge skipped: cannot read settings: %s", exc)
        return
    if not token:
        logger.info("Discord bridge skipped: no Discord bot token configured")
        return
    try:
        _started, message = discord_bridge.start(
            token=token,
            guild_id=guild_id,
            base_url=base_url,
            api_token=api_token,
            db_path=db_path,
        )
        logger.info(message)
    except Exception as exc:  # pragma: no cover - adapter failure
        logger.warning("Discord bridge failed to start: %s", exc)
