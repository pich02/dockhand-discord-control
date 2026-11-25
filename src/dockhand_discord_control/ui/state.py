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


def _text(value: object) -> str:
    """Return *value* as a stripped string.

    The browser can send ``null`` for an input that was never filled in, and a
    ``None`` in a state variable would make ``str.strip()`` raise.  Normalising
    here keeps the save handler free of exceptions.
    """
    if value is None:
        return ""
    return str(value).strip()


#: Instance attribute that holds the injected collaborators.  They contain
#: SQLite connections, locks and threads, which cannot be pickled, so they are
#: kept in a single attribute that is left out of the serialized state and
#: recreated on demand.
_COLLABORATOR_ATTR = "_AppState__collaborators"

#: Keys of the collaborator mapping.
_COLLABORATOR_KEYS = (
    "settings_repo",
    "mapping_repo",
    "snapshot_use_case",
    "discord_bridge",
    "token_verifier",
    "owns_snapshot_use_case",
)


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

    def remove_mapping(self, channel_id: str) -> None: ...


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
    original_channel_id: str


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
    new_mapping_container_name: str = ""
    new_mapping_channel_id: str = ""
    new_mapping_enabled: bool = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        settings_repo = kwargs.pop("settings_repo", None)
        mapping_repo = kwargs.pop("mapping_repo", None)
        snapshot_use_case = kwargs.pop("snapshot_use_case", None)
        discord_bridge = kwargs.pop("discord_bridge", None)
        token_verifier = kwargs.pop("token_verifier", None)

        if args:
            parent_state = args[0]
            if len(args) >= 2:
                kwargs.setdefault("init_substates", args[1])
            if len(args) >= 3:
                kwargs.setdefault("_reflex_internal_init", args[2])
        else:
            parent_state = kwargs.get("parent_state")

        init_bookkeeping = getattr(self, "_init_bookkeeping", None)
        if callable(init_bookkeeping):
            init_bookkeeping(parent_state)

        super().__init__(*args, **kwargs)

        # Dependency-injected collaborators.  They live in a single instance
        # attribute that is not a class field, so Reflex does not treat them
        # as state vars and does not try to serialize them.
        self.__collaborators: dict[str, Any] = dict.fromkeys(_COLLABORATOR_KEYS)
        self.__collaborators.update(
            settings_repo=settings_repo,
            mapping_repo=mapping_repo,
            snapshot_use_case=snapshot_use_case,
            discord_bridge=discord_bridge,
            token_verifier=token_verifier,
            # An injected use case is owned by the caller and must not be
            # replaced; a lazily built one is rebuilt after a save.
            owns_snapshot_use_case=snapshot_use_case is None,
        )

    # -- collaborators ----------------------------------------------------

    def __getstate__(self) -> dict[str, Any]:
        """Return the serializable state, without the collaborators."""
        state = dict(super().__getstate__())
        state.pop(_COLLABORATOR_ATTR, None)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore the state and drop the collaborators (recreated lazily)."""
        super().__setstate__(state)
        self.__collaborators = dict.fromkeys(_COLLABORATOR_KEYS)
        # The restored state owns its Dockhand client again.
        self.__collaborators["owns_snapshot_use_case"] = True

    def _settings_repo(self) -> _SettingsRepository:
        repo = self.__collaborators["settings_repo"]
        if repo is None:
            from dockhand_discord_control.persistence import (
                Settings,
                SqliteSettingsRepository,
            )

            repo = SqliteSettingsRepository(Settings().db_path)
            self.__collaborators["settings_repo"] = repo
        return repo

    def _mapping_repo(self) -> _ChannelMappingRepository:
        repo = self.__collaborators["mapping_repo"]
        if repo is None:
            from dockhand_discord_control.persistence import (
                Settings,
                SqliteChannelMappingRepository,
            )

            repo = SqliteChannelMappingRepository(Settings().db_path)
            self.__collaborators["mapping_repo"] = repo
        return repo

    def _snapshot_use_case(self) -> _SnapshotUseCase:
        use_case = self.__collaborators["snapshot_use_case"]
        if use_case is None:
            from dockhand_discord_control.dockhand.client import DockhandApiClient
            from dockhand_discord_control.domain.use_cases import SnapshotUseCase

            use_case = SnapshotUseCase(
                DockhandApiClient(
                    base_url=self.dockhand_base_url,
                    api_token=self.dockhand_api_token,
                )
            )
            self.__collaborators["snapshot_use_case"] = use_case
        return use_case

    def _discord_bridge(self) -> _DiscordBridge:
        bridge = self.__collaborators["discord_bridge"]
        if bridge is None:
            from dockhand_discord_control.ui.bridge import discord_bridge

            bridge = discord_bridge
            self.__collaborators["discord_bridge"] = bridge
        return bridge

    def _token_verifier(self) -> Callable[[str], str | None]:
        verifier = self.__collaborators["token_verifier"]
        if verifier is None:
            from dockhand_discord_control.ui.bridge import verify_discord_token

            verifier = verify_discord_token
            self.__collaborators["token_verifier"] = verifier
        return verifier

    @staticmethod
    def _db_path() -> str:
        """Return the configured SQLite database path."""
        from dockhand_discord_control.persistence import Settings

        return Settings().db_path

    # -- settings ---------------------------------------------------------

    @rx.event
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

    @rx.event
    async def save_settings(self):  # type: ignore[override]
        """Persist dockhand and Discord settings, then verify the connections.

        The handler is asynchronous because the verification steps talk to the
        network and to the Discord bot thread; they run in worker threads so
        the Reflex event loop stays responsive.

        Every failure is reported through ``status_message``; nothing in this
        handler may raise, otherwise the UI would stay silent.
        """
        try:
            base_url = _text(self.dockhand_base_url)
            api_token = _text(self.dockhand_api_token)
            discord_token = _text(self.discord_bot_token)
            guild_id = _text(self.discord_guild_id)
            logger.info(
                "save_settings called: base_url set=%s, api_token set=%s, "
                "discord_token set=%s, guild_id set=%s",
                bool(base_url),
                bool(api_token),
                bool(discord_token),
                bool(guild_id),
            )
            if not base_url or not api_token:
                logger.warning(
                    "save_settings aborted: the Dockhand base URL and API token are "
                    "required (base_url set=%s, api_token set=%s)",
                    bool(base_url),
                    bool(api_token),
                )
                self.status_message = "Dockhand base URL and API token are required."
                return
            self.status_message = "Saving settings..."
            yield
            repo = self._settings_repo()
            logger.info("save_settings: writing the settings to %s", self._db_path())
            repo.set_dockhand_settings(base_url, api_token)
            repo.set_discord_token(discord_token or None)
            repo.set_discord_guild_id(guild_id or None)
        except Exception as exc:
            logger.exception("save_settings failed")
            self.status_message = f"Failed to save settings: {exc}"
            return
        logger.info("save_settings: the settings were persisted")
        self.dockhand_base_url = base_url
        self.dockhand_api_token = api_token
        # The Dockhand client is rebuilt from the saved values.
        if self.__collaborators["owns_snapshot_use_case"]:
            old_use_case = self.__collaborators["snapshot_use_case"]
            self.__collaborators["snapshot_use_case"] = None
            old_client = getattr(old_use_case, "_client", None)
            close = getattr(old_client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover - best effort
                    logger.warning(
                        "Dockhand client did not close cleanly", exc_info=True
                    )
        try:
            # Resolve the use case on the event loop thread; the worker only
            # calls it, so the cached use case is never mutated off-loop.
            use_case = self._snapshot_use_case()
            dockhand_message = await asyncio.to_thread(
                self._check_dockhand_connection, use_case
            )
            discord_message, bot_status = await asyncio.to_thread(
                self._apply_discord_settings,
                discord_token,
                guild_id,
                base_url,
                api_token,
            )
        except Exception as exc:
            logger.exception("save_settings verification failed")
            self.discord_bot_status = f"Verification failed: {exc}"
            self.status_message = f"Settings saved. Verification failed: {exc}"
            return
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

    @rx.event
    async def load_dashboard(self) -> None:
        """Load settings then refresh the status snapshot for the dashboard."""
        self.load_settings()
        self.discord_bot_status = self._discord_bridge().status()
        if not self.dockhand_base_url or not self.dockhand_api_token:
            self.status_message = "Configure Dockhand settings to load status."
            return
        await self.refresh_status()

    @rx.event
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

    @rx.event
    def set_dockhand_base_url(self, value: str) -> None:
        self.dockhand_base_url = _text(value)

    @rx.event
    def set_dockhand_api_token(self, value: str) -> None:
        self.dockhand_api_token = _text(value)

    @rx.event
    def set_discord_bot_token(self, value: str) -> None:
        self.discord_bot_token = _text(value)

    @rx.event
    def set_discord_guild_id(self, value: str) -> None:
        self.discord_guild_id = _text(value)

    @rx.event
    def set_new_mapping_container_name(self, value: str) -> None:
        self.new_mapping_container_name = _text(value)

    @rx.event
    def set_new_mapping_channel_id(self, value: str) -> None:
        self.new_mapping_channel_id = _text(value)

    @rx.event
    def set_new_mapping_enabled(self, value: bool) -> None:
        self.new_mapping_enabled = bool(value)

    @rx.var
    def container_names(self) -> list[str]:
        """Names of known containers, for the add-mapping selector."""
        return [container.name for container in self.containers]

    # -- mappings ---------------------------------------------------------

    @rx.event
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
                            original_channel_id=mapping.channel_id,
                        )
                    )
        except Exception as exc:
            logger.exception("load_mappings failed")
            self.status_message = f"Failed to load mappings: {exc}"
            return
        self.mappings = loaded
        self.status_message = f"Loaded {len(loaded)} mapping(s)."

    @rx.event
    def add_mapping(self) -> None:
        """Create a mapping from the add-mapping form."""
        container_name = _text(self.new_mapping_container_name)
        channel_id = _text(self.new_mapping_channel_id)
        enabled = bool(self.new_mapping_enabled)
        if not container_name:
            self.status_message = "Select a container to map."
            return
        if not channel_id:
            self.status_message = "Channel ID is required."
            return
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
            logger.exception("add_mapping failed")
            self.status_message = f"Failed to add mapping: {exc}"
            return
        self.new_mapping_channel_id = ""
        self._upsert_mapping(container_name, channel_id, enabled)
        self.status_message = (
            f"Mapping added for {container_name} on channel {channel_id}."
        )

    @rx.event
    def save_mapping(
        self,
        container_name: str,
        channel_id: str,
        enabled: bool,
        original_channel_id: str = "",
    ) -> None:
        """Upsert a channel mapping and refresh the in-state list."""
        container_name = _text(container_name)
        channel_id = _text(channel_id)
        original_channel_id = _text(original_channel_id)
        if not container_name:
            self.status_message = "Container name is required."
            return
        if not channel_id:
            self.status_message = "Channel ID is required."
            return
        new_mapping_persisted = False
        try:
            repo = self._mapping_repo()
            repo.add_mapping(
                ChannelMapping(
                    container_name=container_name,
                    channel_id=channel_id,
                    enabled=enabled,
                )
            )
            new_mapping_persisted = True
            if original_channel_id and original_channel_id != channel_id:
                repo.remove_mapping(original_channel_id)
        except Exception as exc:
            logger.exception("save_mapping failed")
            if new_mapping_persisted:
                try:
                    self.load_mappings()
                except Exception:  # pragma: no cover - best effort reload
                    logger.exception("save_mapping reload after partial write failed")
            self.status_message = f"Failed to save mapping: {exc}"
            return
        self._upsert_mapping(
            container_name,
            channel_id,
            enabled,
            original_channel_id=original_channel_id or channel_id,
        )
        self.status_message = (
            f"Mapping saved for {container_name} on channel {channel_id}."
        )

    @rx.event
    def update_mapping_channel_id(self, index: int, value: str) -> None:
        """Update the channel_id draft for a mapping row."""
        if index < 0 or index >= len(self.mappings):
            return
        updated: list[_Mapping] = []
        for i, current in enumerate(self.mappings):
            if i == index:
                updated.append(
                    _Mapping(
                        container_name=current["container_name"],
                        channel_id=_text(value),
                        enabled=current["enabled"],
                        original_channel_id=current.get(
                            "original_channel_id", current["channel_id"]
                        ),
                    )
                )
            else:
                updated.append(_Mapping(**current))
        self.mappings = updated

    @rx.event
    def update_mapping_enabled(self, index: int, value: bool) -> None:
        """Update the enabled draft for a mapping row."""
        if index < 0 or index >= len(self.mappings):
            return
        updated: list[_Mapping] = []
        for i, current in enumerate(self.mappings):
            if i == index:
                updated.append(
                    _Mapping(
                        container_name=current["container_name"],
                        channel_id=current["channel_id"],
                        enabled=bool(value),
                        original_channel_id=current.get(
                            "original_channel_id", current["channel_id"]
                        ),
                    )
                )
            else:
                updated.append(_Mapping(**current))
        self.mappings = updated

    @rx.event
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
                        original_channel_id=current.get(
                            "original_channel_id", channel_id
                        ),
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
        self,
        container_name: str,
        channel_id: str,
        enabled: bool,
        original_channel_id: str = "",
    ) -> None:
        match_channel_id = _text(original_channel_id) or channel_id
        entry = _Mapping(
            container_name=container_name,
            channel_id=channel_id,
            enabled=enabled,
            original_channel_id=channel_id,
        )
        updated = False
        new_mappings: list[_Mapping] = []
        for current in self.mappings:
            current_original = current.get("original_channel_id", current["channel_id"])
            if (
                current["container_name"] == container_name
                and current_original == match_channel_id
            ):
                new_mappings.append(entry)
                updated = True
            else:
                new_mappings.append(_Mapping(**current))
        if not updated:
            new_mappings.append(entry)
        self.mappings = new_mappings

    # -- status -----------------------------------------------------------

    @rx.event
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
