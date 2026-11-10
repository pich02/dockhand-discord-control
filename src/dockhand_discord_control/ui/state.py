"""Reflex application state for the Dockhand Discord Control web UI.

The state is dependency-injected: its constructor accepts the persistence
repositories and domain use cases it delegates to.  When the Reflex app
constructs the state itself (no arguments) the real SQLite adapters are
created lazily; tests can inject fakes directly.

The collaborators are stored as name-mangled instance attributes so Reflex does
not treat them as serializable state vars.
"""

from __future__ import annotations

import logging
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

    def set_dockhand_settings(self, base_url: str, token: str) -> None: ...

    def set_discord_token(self, token: str | None) -> None: ...


class _ChannelMappingRepository(Protocol):
    """Read/write channel-mapping repository used by the UI."""

    def mappings_for_container(self, container_name: str) -> list[ChannelMapping]: ...

    def add_mapping(self, mapping: ChannelMapping) -> None: ...

    def set_enabled(self, channel_id: str, enabled: bool) -> None: ...


class _SnapshotUseCase(Protocol):
    """Snapshot use case used by the UI."""

    def execute(self) -> Snapshot: ...


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
    mappings: list[_Mapping] = []

    def __init__(
        self,
        parent_state: BaseState | None = None,
        init_substates: bool = True,
        _reflex_internal_init: bool = False,
        settings_repo: _SettingsRepository | None = None,
        mapping_repo: _ChannelMappingRepository | None = None,
        snapshot_use_case: _SnapshotUseCase | None = None,
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

    # -- collaborators ----------------------------------------------------

    def _settings_repo(self) -> _SettingsRepository:
        repo = self.__settings_repo
        if repo is None:
            from dockhand_discord_control.persistence import SqliteSettingsRepository

            repo = SqliteSettingsRepository()
            self.__settings_repo = repo
        return repo

    def _mapping_repo(self) -> _ChannelMappingRepository:
        repo = self.__mapping_repo
        if repo is None:
            from dockhand_discord_control.persistence import (
                SqliteChannelMappingRepository,
            )

            repo = SqliteChannelMappingRepository()
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

    # -- settings ---------------------------------------------------------

    def load_settings(self) -> None:
        """Load dockhand and Discord settings from the repository."""
        repo = self._settings_repo()
        base_url, token = repo.get_dockhand_settings()
        self.dockhand_base_url = base_url
        self.dockhand_api_token = token
        self.discord_bot_token = repo.get_discord_token() or ""
        self.status_message = "Settings loaded."

    def save_settings(self) -> None:
        """Persist dockhand and Discord settings after validation."""
        if not self.dockhand_base_url or not self.dockhand_api_token:
            self.status_message = "Dockhand base URL and API token are required."
            return
        repo = self._settings_repo()
        repo.set_dockhand_settings(self.dockhand_base_url, self.dockhand_api_token)
        repo.set_discord_token(self.discord_bot_token or None)
        self.status_message = "Settings saved."

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
        repo = self._mapping_repo()
        loaded: list[_Mapping] = []
        for container in self.containers:
            for mapping in repo.mappings_for_container(container.name):
                loaded.append(
                    _Mapping(
                        container_name=mapping.container_name,
                        channel_id=mapping.channel_id,
                        enabled=mapping.enabled,
                    )
                )
        self.mappings = loaded
        self.status_message = f"Loaded {len(loaded)} mapping(s)."

    def save_mapping(self, container_name: str, channel_id: str, enabled: bool) -> None:
        """Upsert a channel mapping and refresh the in-state list."""
        repo = self._mapping_repo()
        repo.add_mapping(
            ChannelMapping(
                container_name=container_name,
                channel_id=channel_id,
                enabled=enabled,
            )
        )
        self._upsert_mapping(container_name, channel_id, enabled)
        self.status_message = (
            f"Mapping saved for {container_name} on channel {channel_id}."
        )

    def toggle_mapping(self, container_name: str, channel_id: str) -> None:
        """Flip the enabled flag of a channel mapping."""
        repo = self._mapping_repo()
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
        repo.set_enabled(channel_id, new_enabled)
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

    def refresh_status(self) -> None:
        """Refresh the environments/containers snapshot via the use case."""
        try:
            snapshot = self._snapshot_use_case().execute()
        except Exception as exc:  # keep the UI alive on adapter failure
            logger.exception("refresh_status failed")
            self.status_message = f"Failed to refresh status: {exc}"
            return
        self.environments = list(snapshot.environments)
        self.containers = list(snapshot.containers)
        self.status_message = (
            f"Loaded {len(snapshot.environments)} environment(s), "
            f"{len(snapshot.containers)} container(s)."
        )
