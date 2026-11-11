"""Reflex application wiring for the Dockhand Discord Control web UI.

:func:`build_app` creates the :class:`reflex.app.App`, registers the UI pages
and starts the Discord bridge as a best-effort background daemon thread.
"""

from __future__ import annotations

import logging
import threading

import reflex as rx

from dockhand_discord_control.discord import DiscordBot
from dockhand_discord_control.discord.commands import DiscordCommandHandlers
from dockhand_discord_control.dockhand.client import DockhandApiClient
from dockhand_discord_control.domain.use_cases import (
    RestartContainerUseCase,
    SnapshotUseCase,
    StartContainerUseCase,
    StopContainerUseCase,
)
from dockhand_discord_control.persistence import (
    Settings,
    SqliteChannelMappingRepository,
    SqliteSettingsRepository,
)

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
    keeps running.
    """
    try:
        db_path = Settings().db_path
        settings_repo = SqliteSettingsRepository(db_path)
        token = settings_repo.get_discord_token()
    except Exception as exc:  # pragma: no cover - infrastructure failure
        logger.warning("Discord bridge skipped: cannot read settings: %s", exc)
        return
    if not token:
        logger.info("Discord bridge skipped: no Discord bot token configured")
        return
    try:
        bot = DiscordBot(
            token=token,
            handlers=_build_command_handlers(settings_repo, db_path),
            guild_id=settings_repo.get_discord_guild_id(),
        )
        thread = threading.Thread(
            target=bot.run,
            daemon=True,
            name="discord-bridge",
        )
        thread.start()
        logger.info("Discord bridge started in background thread")
    except Exception as exc:  # pragma: no cover - adapter failure
        logger.warning("Discord bridge failed to start: %s", exc)


def _build_command_handlers(
    settings_repo: SqliteSettingsRepository,
    db_path: str = "./data/app.sqlite",
) -> DiscordCommandHandlers:
    base_url, api_token = settings_repo.get_dockhand_settings()
    client = DockhandApiClient(base_url=base_url, api_token=api_token)
    mapping_repo = SqliteChannelMappingRepository(db_path)
    return DiscordCommandHandlers(
        snapshot_use_case=SnapshotUseCase(client),
        start_use_case=StartContainerUseCase(client, mapping_repo),
        stop_use_case=StopContainerUseCase(client, mapping_repo),
        restart_use_case=RestartContainerUseCase(client, mapping_repo),
        mapping_repo=mapping_repo,
    )
