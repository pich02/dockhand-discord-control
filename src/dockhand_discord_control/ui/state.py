"""Reflex application state for the Dockhand Discord Control web UI.

The state is dependency-injected: its constructor accepts the persistence
repositories and domain use cases it delegates to.  When the Reflex app
constructs the state itself (no arguments) the real SQLite adapters are
created lazily; tests can inject fakes directly.

The collaborators are stored as name-mangled instance attributes so Reflex does
not treat them as serializable state vars.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Protocol, TypedDict

import reflex as rx
from reflex.state import BaseState

from dockhand_discord_control.domain.models import (
    ChannelMapping,
    DockerContainer,
    DockhandEnvironment,
    Snapshot,
)

logger = logging.getLogger(__name__)


class _SettingsRepository(Protocol):
    """Read/write settings repository used by the UI.

    The domain :class:`dockhand_discord_control.domain.ports.SettingsRepository`
    port exposes the getters; the SQLite persistence adapter adds the setters
    below.  The UI depends on the full read/write interface.
    """

    def get_dockhand_settings(self) -> tuple[str, str]: ...

    def get_discord_token(self) -> str | None: ...

    def get_discord_guild_id(self) -> str | None: ...

    def set_dockhand_settings(self, base_url: str, token: str) -> None: ...

    def set_discord_token(self, token: str | None) -> None: ...

    def set_discord_guild_id(self, guild_id: str | None) -> None: ...


class _ChannelMappingRepository(Protocol):
    """Read/write channel-mapping repository used by the UI."""

    def mappings_for_container(self, container_name: str) -> list[ChannelMapping]: ...

    def add_mapping(self, mapping: ChannelMapping) -> None: ...

    def set_enabled(self, channel_id: str, enabled: bool) -> None: ...


class _SnapshotUseCase(Protocol):
    """Snapshot use case used by the UI."""

    def execute(self) -> Snapshot: ...


class _DiscordBridge(Protocol):
    """Discord bridge lifecycle used by the UI."""

    def start(
        self,
        *,
        token: str | None,
        guild_id: str | None,
        base_url: str,
        api_token: str,
        db_path: str,
    ) -> tuple[bool, str]: ...

    def stop(self) -> None: ...

    def status(self) -> str: ...


class _Mapping(TypedDict):
    """A row rendered by the mappings page."""

    container_name: str
    channel_id: str
    enabled: bool


class AppState(rx.State):
    """Application state for the Reflex web UI."""

    dockhand_base_url: str = ""
    dockhand_api_token: str = ""
    discord_bot_token: str = ""
    discord_guild_id: str = ""
    environments: list[DockhandEnvironment] = []
    containers: list[DockerContainer] = []
    status_message: str = ""
    discord_bot_status: str = ""
    mappings: list[_Mapping] = []

    def __init__(
        self,
        parent_state: BaseState | None = None,
        init_substates: bool = True,
        _reflex_internal_init: bool = False,
        settings_repo: _SettingsRepository | None = None,
        mapping_repo: _ChannelMappingRepository | None = None,
        snapshot_use_case: _SnapshotUseCase | None = None,
        discord_bridge: _DiscordBridge | None = None,
        token_verifier: Callable[[str], str | None] | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward the Reflex-internal init flags so the framework can
        # instantiate the state directly during compilation (e.g.
        # ``compile_state`` calls ``state(_reflex_internal_init=True)``)
        # without tripping the "do not instantiate state directly" guard.
        self._init_bookkeeping(parent_state)
        # pyright cannot infer pydantic's dynamically generated ``__init__``
        # signature, so these legitimate Reflex-internal flags are ignored here.
        super().__init__(
            parent_state=parent_state,
            init_substates=init_substates,  # type: ignore[call-arg]
            _reflex_internal_init=_reflex_internal_init,  # type: ignore[call-arg]
            **kwargs,
        )
        # Dependency-injected collaborators.  Name-mangled instance attributes
        # are not class fields, so Reflex does not treat them as state vars.
        self.__settings_repo = settings_repo
        self.__mapping_repo = mapping_repo
        self.__snapshot_use_case = snapshot_use_case
        # An injected use case is owned by the caller and must not be replaced.
        self.__owns_snapshot_use_case = snapshot_use_case is None
        self.__discord_bridge = discord_bridge
        self.__token_verifier = token_verifier

    # -- collaborators ----------------------------------------------------

    def _settings_repo(self) -> _SettingsRepository:
        repo = self.__settings_repo
        if repo is None:
            from dockhand_discord_control.persistence import (
                Settings,
                SqliteSettingsRepository,
            )

            repo = SqliteSettingsRepository(Settings().db_path)
            self.__settings_repo = repo
        return repo

    def _mapping_repo(self) -> _ChannelMappingRepository:
        repo = self.__mapping_repo
        if repo is None:
            from dockhand_discord_control.persistence import (
                Settings,
                SqliteChannelMappingRepository,
            )

            repo = SqliteChannelMappingRepository(Settings().db_path)
            self.__mapping_repo = repo
        return repo

    def _snapshot_use_case(self) -> _SnapshotUseCase:
        use_case = self.__snapshot_use_case
        if use_case is None:
            from dockhand_discord_control.dockhand.client import DockhandApiClient
            from dockhand_discord_control.domain.use_cases import SnapshotUseCase

            use_case = SnapshotUseCase(
                DockhandApiClient(
                    base_url=self.dockhand_base_url,
                    api_token=self.dockhand_api_token,
                )
            )
            self.__snapshot_use_case = use_case
        return use_case

    def _discord_bridge(self) -> _DiscordBridge:
        bridge = self.__discord_bridge
        if bridge is None:
            from dockhand_discord_control.ui.bridge import discord_bridge

            bridge = discord_bridge
            self.__discord_bridge = bridge
        return bridge

    def _token_verifier(self) -> Callable[[str], str | None]:
        verifier = self.__token_verifier
        if verifier is None:
            from dockhand_discord_control.ui.bridge import verify_discord_token

            verifier = verify_discord_token
            self.__token_verifier = verifier
        return verifier

    @staticmethod
    def _db_path() -> str:
        """Return the configured SQLite database path."""
        from dockhand_discord_control.persistence import Settings

        return Settings().db_path

    # -- settings ---------------------------------------------------------

    def load_settings(self) -> None:
        """Load dockhand and Discord settings from the repository."""
        try:
            repo = self._settings_repo()
            base_url, token = repo.get_dockhand_settings()
            discord_token = repo.get_discord_token() or ""
            guild_id = repo.get_discord_guild_id() or ""
        except Exception as exc:
            logger.exception("load_settings failed")
            self.status_message = f"Failed to load settings: {exc}"
            return
        self.dockhand_base_url = base_url
        self.dockhand_api_token = token
        self.discord_bot_token = discord_token
        self.discord_guild_id = guild_id
        self.status_message = "Settings loaded."

    async def save_settings(self) -> None:
        """Persist dockhand and Discord settings, then verify the connections.

        The handler is asynchronous because the verification steps talk to the
        network and to the Discord bot thread; they run in worker threads so
        the Reflex event loop stays responsive.
        """
        base_url = self.dockhand_base_url.strip()
        api_token = self.dockhand_api_token.strip()
        discord_token = self.discord_bot_token.strip()
        guild_id = self.discord_guild_id.strip()
        if not base_url or not api_token:
            self.status_message = "Dockhand base URL and API token are required."
            return
        try:
            repo = self._settings_repo()
            repo.set_dockhand_settings(base_url, api_token)
            repo.set_discord_token(discord_token or None)
            repo.set_discord_guild_id(guild_id or None)
        except Exception as exc:
            logger.exception("save_settings failed")
            self.status_message = f"Failed to save settings: {exc}"
            return
        self.dockhand_base_url = base_url
        self.dockhand_api_token = api_token
        # The Dockhand client is rebuilt from the saved values.
        if self.__owns_snapshot_use_case:
            self.__snapshot_use_case = None
        # Resolve the use case on the event loop thread; the worker only calls
        # it, so the cached use case is never mutated off-loop.
        use_case = self._snapshot_use_case()
        dockhand_message = await asyncio.to_thread(
            self._check_dockhand_connection, use_case
        )
        discord_message, bot_status = await asyncio.to_thread(
            self._apply_discord_settings, discord_token, guild_id, base_url, api_token
        )
        self.discord_bot_status = bot_status
        self.status_message = " ".join(
            ["Settings saved.", dockhand_message, discord_message]
        )

    def _check_dockhand_connection(self, use_case: _SnapshotUseCase) -> str:
        """Verify the Dockhand API answers with the saved credentials."""
        try:
            snapshot = use_case.execute()
        except Exception as exc:
            logger.warning("Dockhand connection check failed: %s", exc)
            return f"Dockhand connection failed: {exc}"
        return (
            f"Dockhand reachable ({len(snapshot.environments)} environment(s), "
            f"{len(snapshot.containers)} container(s))."
        )

    def _apply_discord_settings(
        self, token: str, guild_id: str, base_url: str, api_token: str
    ) -> tuple[str, str]:
        """Start, restart or stop the Discord bridge to match the settings.

        Returns the message for the status line and the current bot status.
        Runs in a worker thread, so it must not touch Reflex state vars.
        """
        bridge = self._discord_bridge()
        if not token:
            try:
                bridge.stop()
            except Exception as exc:  # pragma: no cover - shutdown best effort
                logger.warning("Could not stop the Discord bot: %s", exc)
            return "Discord bot not started: no bot token configured.", bridge.status()
        try:
            warning = self._token_verifier()(token)
        except Exception as exc:
            logger.warning("Discord token check failed: %s", exc)
            warning = f"the token could not be checked ({exc})"
        try:
            _started, message = bridge.start(
                token=token,
                guild_id=guild_id or None,
                base_url=base_url,
                api_token=api_token,
                db_path=self._db_path(),
            )
        except Exception as exc:
            logger.exception("Could not start the Discord bot")
            return f"Discord bot failed to start: {exc}", f"Discord bot failed: {exc}"
        status = bridge.status()
        if warning:
            return f"{message} Token check: {warning}.", status
        return message, status

    async def load_dashboard(self) -> None:
        """Load settings then refresh the status snapshot for the dashboard."""
        self.load_settings()
        self.discord_bot_status = self._discord_bridge().status()
        if not self.dockhand_base_url or not self.dockhand_api_token:
            self.status_message = "Configure Dockhand settings to load status."
            return
        await self.refresh_status()

    async def load_mappings_page(self) -> None:
        """Load settings, ensure containers are available, then load mappings."""
        self.load_settings()
        self.discord_bot_status = self._discord_bridge().status()
        if not self.dockhand_base_url or not self.dockhand_api_token:
            self.status_message = "Configure Dockhand settings to load mappings."
            return
        if not self.containers:
            await self.refresh_status()
        self.load_mappings()

    def set_dockhand_base_url(self, value: str) -> None:
        self.dockhand_base_url = value

    def set_dockhand_api_token(self, value: str) -> None:
        self.dockhand_api_token = value

    def set_discord_bot_token(self, value: str) -> None:
        self.discord_bot_token = value

    def set_discord_guild_id(self, value: str) -> None:
        self.discord_guild_id = value

    # -- mappings ---------------------------------------------------------

    def load_mappings(self) -> None:
        """Load all channel mappings for the known containers."""
        loaded: list[_Mapping] = []
        try:
            repo = self._mapping_repo()
            for container in self.containers:
                for mapping in repo.mappings_for_container(container.name):
                    loaded.append(
                        _Mapping(
                            container_name=mapping.container_name,
                            channel_id=mapping.channel_id,
                            enabled=mapping.enabled,
                        )
                    )
        except Exception as exc:
            logger.exception("load_mappings failed")
            self.status_message = f"Failed to load mappings: {exc}"
            return
        self.mappings = loaded
        self.status_message = f"Loaded {len(loaded)} mapping(s)."

    def save_mapping(self, container_name: str, channel_id: str, enabled: bool) -> None:
        """Upsert a channel mapping and refresh the in-state list."""
        try:
            repo = self._mapping_repo()
            repo.add_mapping(
                ChannelMapping(
                    container_name=container_name,
                    channel_id=channel_id,
                    enabled=enabled,
                )
            )
        except Exception as exc:
            logger.exception("save_mapping failed")
            self.status_message = f"Failed to save mapping: {exc}"
            return
        self._upsert_mapping(container_name, channel_id, enabled)
        self.status_message = (
            f"Mapping saved for {container_name} on channel {channel_id}."
        )

    def toggle_mapping(self, container_name: str, channel_id: str) -> None:
        """Flip the enabled flag of a channel mapping."""
        new_enabled = False
        found = False
        updated: list[_Mapping] = []
        for current in self.mappings:
            if (
                current["container_name"] == container_name
                and current["channel_id"] == channel_id
            ):
                new_enabled = not current["enabled"]
                found = True
                updated.append(
                    _Mapping(
                        container_name=container_name,
                        channel_id=channel_id,
                        enabled=new_enabled,
                    )
                )
            else:
                updated.append(_Mapping(**current))
        if not found:
            self.status_message = (
                f"No mapping for {container_name} on channel {channel_id}."
            )
            return
        try:
            repo = self._mapping_repo()
            repo.set_enabled(channel_id, new_enabled)
        except Exception as exc:
            logger.exception("toggle_mapping failed")
            self.status_message = f"Failed to update mapping: {exc}"
            return
        self.mappings = updated
        self.status_message = (
            f"Mapping {'enabled' if new_enabled else 'disabled'} "
            f"for {container_name} on channel {channel_id}."
        )

    def _upsert_mapping(
        self, container_name: str, channel_id: str, enabled: bool
    ) -> None:
        entry = _Mapping(
            container_name=container_name, channel_id=channel_id, enabled=enabled
        )
        updated = False
        new_mappings: list[_Mapping] = []
        for current in self.mappings:
            if (
                current["container_name"] == container_name
                and current["channel_id"] == channel_id
            ):
                new_mappings.append(entry)
                updated = True
            else:
                new_mappings.append(_Mapping(**current))
        if not updated:
            new_mappings.append(entry)
        self.mappings = new_mappings

    # -- status -----------------------------------------------------------

    async def refresh_status(self) -> None:
        """Refresh the environments/containers snapshot via the use case.

        The Dockhand call is a network request, so it runs in a worker thread
        to keep the Reflex event loop responsive.
        """
        try:
            use_case = self._snapshot_use_case()
            snapshot = await asyncio.to_thread(use_case.execute)
        except Exception as exc:  # keep the UI alive on adapter failure
            logger.exception("refresh_status failed")
            self.status_message = f"Failed to refresh status: {exc}"
            self.discord_bot_status = self._discord_bridge().status()
            return
        self.environments = list(snapshot.environments)
        self.containers = list(snapshot.containers)
        self.discord_bot_status = self._discord_bridge().status()
        self.status_message = (
            f"Loaded {len(snapshot.environments)} environment(s), "
            f"{len(snapshot.containers)} container(s)."
        )
