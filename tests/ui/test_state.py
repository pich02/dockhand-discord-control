"""Tests for the Reflex application state with fakes for the collaborators.

No :mod:`reflex` rendering and no network are involved; the state methods are
tested directly with injected fakes.
"""

from __future__ import annotations

import asyncio
import inspect
import pickle
import threading
from pathlib import Path

import pytest

from dockhand_discord_control.domain.models import (
    ChannelMapping,
    ContainerStatus,
    DockerContainer,
    DockhandEnvironment,
    EnvironmentStatus,
    Snapshot,
)
from dockhand_discord_control.ui.state import AppState


class FakeSettingsRepository:
    """In-memory fake for the settings repository (read/write)."""

    def __init__(
        self,
        base_url: str = "",
        token: str = "",
        discord_token: str | None = None,
        discord_guild_id: str | None = None,
    ) -> None:
        self._base_url = base_url
        self._token = token
        self._discord_token = discord_token
        self._discord_guild_id = discord_guild_id
        self.saved_dockhand: tuple[str, str] | None = None
        self.saved_discord: str | None = None
        self.saved_discord_guild_id: str | None = None

    def get_dockhand_settings(self) -> tuple[str, str]:
        return self._base_url, self._token

    def get_discord_token(self) -> str | None:
        return self._discord_token

    def get_discord_guild_id(self) -> str | None:
        return self._discord_guild_id

    def set_dockhand_settings(self, base_url: str, token: str) -> None:
        self.saved_dockhand = (base_url, token)
        self._base_url = base_url
        self._token = token

    def set_discord_token(self, token: str | None) -> None:
        self.saved_discord = token
        self._discord_token = token

    def set_discord_guild_id(self, guild_id: str | None) -> None:
        self.saved_discord_guild_id = guild_id
        self._discord_guild_id = guild_id


class FakeMappingRepository:
    """In-memory fake for the channel-mapping repository (read/write)."""

    def __init__(self, mappings: list[ChannelMapping] | None = None) -> None:
        self._mappings: dict[str, ChannelMapping] = {
            mapping.channel_id: mapping for mapping in (mappings or [])
        }
        self.added: list[ChannelMapping] = []
        self.set_enabled_calls: list[tuple[str, bool]] = []

    def mappings_for_container(self, container_name: str) -> list[ChannelMapping]:
        return [
            mapping
            for mapping in self._mappings.values()
            if mapping.container_name == container_name
        ]

    def add_mapping(self, mapping: ChannelMapping) -> None:
        self.added.append(mapping)
        self._mappings[mapping.channel_id] = mapping

    def set_enabled(self, channel_id: str, enabled: bool) -> None:
        self.set_enabled_calls.append((channel_id, enabled))
        if channel_id in self._mappings:
            current = self._mappings[channel_id]
            self._mappings[channel_id] = ChannelMapping(
                container_name=current.container_name,
                channel_id=channel_id,
                enabled=enabled,
            )


class FakeSnapshotUseCase:
    """Fake for the snapshot use case."""

    def __init__(
        self,
        snapshot: Snapshot | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._snapshot = snapshot or Snapshot(environments=[], containers=[])
        self._exc = exc
        self.called = False

    def execute(self) -> Snapshot:
        self.called = True
        if self._exc is not None:
            raise self._exc
        return self._snapshot


class FakeDiscordBridge:
    """Fake for the Discord bridge lifecycle."""

    def __init__(self, message: str = "Discord bot started.") -> None:
        self._message = message
        self.started: list[dict[str, str | None]] = []
        self.stopped = False

    def start(
        self,
        *,
        token: str | None,
        guild_id: str | None,
        base_url: str,
        api_token: str,
        db_path: str,
    ) -> tuple[bool, str]:
        self.started.append(
            {
                "token": token,
                "guild_id": guild_id,
                "base_url": base_url,
                "api_token": api_token,
                "db_path": db_path,
            }
        )
        return True, self._message

    def stop(self) -> None:
        self.stopped = True

    def status(self) -> str:
        return "Discord bot is running."


def _environment(environment_id: str, name: str) -> DockhandEnvironment:
    return DockhandEnvironment(
        id=environment_id,
        name=name,
        status=EnvironmentStatus.RUNNING,
        base_url=f"http://{name}:8000",
    )


def _container(container_id: str, name: str, environment_id: str) -> DockerContainer:
    return DockerContainer(
        id=container_id,
        name=name,
        image="nginx:latest",
        status=ContainerStatus.RUNNING,
        environment_id=environment_id,
    )


def test_load_settings_reads_from_repository() -> None:
    repo = FakeSettingsRepository(
        base_url="http://dockhand:8080",
        token="dockhand-secret",
        discord_token="bot-token",
        discord_guild_id="guild-1",
    )
    state = AppState(settings_repo=repo)

    state.load_settings()

    assert state.dockhand_base_url == "http://dockhand:8080"
    assert state.dockhand_api_token == "dockhand-secret"
    assert state.discord_bot_token == "bot-token"
    assert state.discord_guild_id == "guild-1"
    assert state.status_message == "Settings loaded."


def test_save_settings_persists_to_repository() -> None:
    repo = FakeSettingsRepository()
    state = AppState(
        settings_repo=repo,
        snapshot_use_case=FakeSnapshotUseCase(),
        discord_bridge=FakeDiscordBridge(),
        token_verifier=lambda _token: None,
    )
    state.dockhand_base_url = "http://dockhand:8080"
    state.dockhand_api_token = "dockhand-secret"
    state.discord_bot_token = "bot-token"
    state.discord_guild_id = "guild-1"

    asyncio.run(state.save_settings())

    assert repo.saved_dockhand == ("http://dockhand:8080", "dockhand-secret")
    assert repo.saved_discord == "bot-token"
    assert repo.saved_discord_guild_id == "guild-1"
    assert "Settings saved." in state.status_message


def test_save_settings_starts_the_discord_bridge() -> None:
    repo = FakeSettingsRepository()
    bridge = FakeDiscordBridge()
    state = AppState(
        settings_repo=repo,
        snapshot_use_case=FakeSnapshotUseCase(),
        discord_bridge=bridge,
        token_verifier=lambda _token: None,
    )
    state.dockhand_base_url = "http://dockhand:8080"
    state.dockhand_api_token = "dockhand-secret"
    state.discord_bot_token = "bot-token"

    asyncio.run(state.save_settings())

    assert len(bridge.started) == 1
    assert bridge.started[0]["token"] == "bot-token"
    assert bridge.started[0]["base_url"] == "http://dockhand:8080"
    assert "Discord bot started." in state.status_message


def test_save_settings_reports_token_check_warning() -> None:
    repo = FakeSettingsRepository()
    state = AppState(
        settings_repo=repo,
        snapshot_use_case=FakeSnapshotUseCase(),
        discord_bridge=FakeDiscordBridge(),
        token_verifier=lambda _token: "the Discord bot token was rejected",
    )
    state.dockhand_base_url = "http://dockhand:8080"
    state.dockhand_api_token = "dockhand-secret"
    state.discord_bot_token = "bad-token"

    asyncio.run(state.save_settings())

    assert "Token check: the Discord bot token was rejected" in state.status_message


def test_save_settings_reports_dockhand_connection_failure() -> None:
    repo = FakeSettingsRepository()
    state = AppState(
        settings_repo=repo,
        snapshot_use_case=FakeSnapshotUseCase(exc=RuntimeError("connection refused")),
        discord_bridge=FakeDiscordBridge(),
        token_verifier=lambda _token: None,
    )
    state.dockhand_base_url = "http://dockhand:8080"
    state.dockhand_api_token = "dockhand-secret"

    asyncio.run(state.save_settings())

    assert "Dockhand connection failed" in state.status_message
    assert "connection refused" in state.status_message
    # The settings are still persisted.
    assert repo.saved_dockhand == ("http://dockhand:8080", "dockhand-secret")


def test_save_settings_reports_persistence_failure() -> None:
    class FailingRepository(FakeSettingsRepository):
        def set_dockhand_settings(self, base_url: str, token: str) -> None:
            raise RuntimeError("database is locked")

    repo = FailingRepository()
    state = AppState(
        settings_repo=repo,
        snapshot_use_case=FakeSnapshotUseCase(),
        discord_bridge=FakeDiscordBridge(),
        token_verifier=lambda _token: None,
    )
    state.dockhand_base_url = "http://dockhand:8080"
    state.dockhand_api_token = "dockhand-secret"

    asyncio.run(state.save_settings())

    assert "Failed to save settings" in state.status_message
    assert "database is locked" in state.status_message


def test_save_settings_without_token_stops_the_bridge() -> None:
    repo = FakeSettingsRepository()
    bridge = FakeDiscordBridge()
    state = AppState(
        settings_repo=repo,
        snapshot_use_case=FakeSnapshotUseCase(),
        discord_bridge=bridge,
        token_verifier=lambda _token: None,
    )
    state.dockhand_base_url = "http://dockhand:8080"
    state.dockhand_api_token = "dockhand-secret"

    asyncio.run(state.save_settings())

    assert bridge.stopped
    assert bridge.started == []
    assert "no bot token configured" in state.status_message


def test_save_settings_is_a_coroutine_handler() -> None:
    assert inspect.iscoroutinefunction(AppState.save_settings.fn)
    assert inspect.iscoroutinefunction(AppState.refresh_status.fn)
    assert inspect.iscoroutinefunction(AppState.load_dashboard.fn)
    assert inspect.iscoroutinefunction(AppState.load_mappings_page.fn)


def test_save_settings_runs_the_dockhand_call_off_the_event_loop() -> None:
    repo = FakeSettingsRepository()
    threads: list[int] = []

    class RecordingUseCase(FakeSnapshotUseCase):
        def execute(self) -> Snapshot:
            threads.append(threading.get_ident())
            return super().execute()

    state = AppState(
        settings_repo=repo,
        snapshot_use_case=RecordingUseCase(),
        discord_bridge=FakeDiscordBridge(),
        token_verifier=lambda _token: None,
    )
    state.dockhand_base_url = "http://dockhand:8080"
    state.dockhand_api_token = "dockhand-secret"

    asyncio.run(state.save_settings())

    assert threads
    assert threads[0] != threading.get_ident()


def test_state_with_a_sqlite_repository_can_be_pickled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The state manager persists the state; the collaborators must not block it."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.sqlite"))
    state = AppState()
    state.load_settings()

    restored = pickle.loads(pickle.dumps(state))

    assert restored.dockhand_base_url == ""
    # The collaborators are recreated on demand after unpickling.
    assert restored._AppState__settings_repo is None


def test_load_settings_reports_read_failure() -> None:
    class FailingRepository(FakeSettingsRepository):
        def get_dockhand_settings(self) -> tuple[str, str]:
            raise RuntimeError("no such table: app_settings")

    state = AppState(settings_repo=FailingRepository())

    state.load_settings()

    assert "Failed to load settings" in state.status_message
    assert "no such table" in state.status_message


def test_save_settings_validates_required_fields() -> None:
    repo = FakeSettingsRepository()
    state = AppState(settings_repo=repo)
    state.dockhand_api_token = "dockhand-secret"

    asyncio.run(state.save_settings())

    assert repo.saved_dockhand is None
    assert repo.saved_discord is None
    assert state.status_message == "Dockhand base URL and API token are required."


def test_settings_setter_methods_update_fields() -> None:
    state = AppState()
    state.set_dockhand_base_url("http://dockhand:8080")
    state.set_dockhand_api_token("dockhand-secret")
    state.set_discord_bot_token("bot-token")
    state.set_discord_guild_id("guild-123")

    assert state.dockhand_base_url == "http://dockhand:8080"
    assert state.dockhand_api_token == "dockhand-secret"
    assert state.discord_bot_token == "bot-token"
    assert state.discord_guild_id == "guild-123"


def test_save_mapping_creates_and_updates() -> None:
    repo = FakeMappingRepository()
    state = AppState(mapping_repo=repo)

    state.save_mapping("web", "ch-1", True)

    assert list(state.mappings) == [
        {"container_name": "web", "channel_id": "ch-1", "enabled": True}
    ]
    assert repo.added == [
        ChannelMapping(container_name="web", channel_id="ch-1", enabled=True)
    ]

    state.save_mapping("web", "ch-1", False)

    assert list(state.mappings) == [
        {"container_name": "web", "channel_id": "ch-1", "enabled": False}
    ]
    # Upserted, not duplicated.
    assert len(state.mappings) == 1


def test_toggle_mapping_flips_enabled_and_persists() -> None:
    repo = FakeMappingRepository(
        mappings=[ChannelMapping(container_name="web", channel_id="ch-1", enabled=True)]
    )
    state = AppState(mapping_repo=repo)
    state.mappings = [{"container_name": "web", "channel_id": "ch-1", "enabled": True}]

    state.toggle_mapping("web", "ch-1")

    assert list(state.mappings) == [
        {"container_name": "web", "channel_id": "ch-1", "enabled": False}
    ]
    assert repo.set_enabled_calls == [("ch-1", False)]

    state.toggle_mapping("web", "ch-1")

    assert state.mappings[0]["enabled"] is True
    assert list(state.mappings) == [
        {"container_name": "web", "channel_id": "ch-1", "enabled": True}
    ]
    assert repo.set_enabled_calls == [("ch-1", False), ("ch-1", True)]


def test_toggle_mapping_unknown_mapping_reports_and_does_not_persist() -> None:
    repo = FakeMappingRepository()
    state = AppState(mapping_repo=repo)

    state.toggle_mapping("web", "ch-1")

    assert repo.set_enabled_calls == []
    assert list(state.mappings) == []
    assert state.status_message == "No mapping for web on channel ch-1."


def test_load_mappings_uses_containers_and_repository() -> None:
    repo = FakeMappingRepository(
        mappings=[
            ChannelMapping(container_name="web", channel_id="ch-1", enabled=True),
            ChannelMapping(container_name="api", channel_id="ch-2", enabled=False),
        ]
    )
    state = AppState(
        mapping_repo=repo,
        containers=[
            _container("c1", "web", "e1"),
            _container("c2", "api", "e1"),
        ],
    )

    state.load_mappings()

    assert list(state.mappings) == [
        {"container_name": "web", "channel_id": "ch-1", "enabled": True},
        {"container_name": "api", "channel_id": "ch-2", "enabled": False},
    ]
    assert "2 mapping(s)" in state.status_message


def test_load_dashboard_loads_settings_and_refreshes() -> None:
    repo = FakeSettingsRepository(
        base_url="http://dockhand:8080",
        token="dockhand-secret",
    )
    env = _environment("e1", "prod")
    container = _container("c1", "web", "e1")
    use_case = FakeSnapshotUseCase(Snapshot(environments=[env], containers=[container]))
    state = AppState(settings_repo=repo, snapshot_use_case=use_case)

    asyncio.run(state.load_dashboard())

    assert state.dockhand_base_url == "http://dockhand:8080"
    assert list(state.environments) == [env]
    assert list(state.containers) == [container]
    assert use_case.called


def test_load_dashboard_missing_config_does_not_request() -> None:
    repo = FakeSettingsRepository()
    use_case = FakeSnapshotUseCase()
    state = AppState(settings_repo=repo, snapshot_use_case=use_case)

    asyncio.run(state.load_dashboard())

    assert "Configure Dockhand settings" in state.status_message
    assert not use_case.called


def test_load_mappings_page_loads_containers_and_mappings() -> None:
    repo = FakeSettingsRepository(
        base_url="http://dockhand:8080",
        token="dockhand-secret",
    )
    mapping_repo = FakeMappingRepository(
        mappings=[ChannelMapping(container_name="web", channel_id="ch-1", enabled=True)]
    )
    env = _environment("e1", "prod")
    container = _container("c1", "web", "e1")
    use_case = FakeSnapshotUseCase(Snapshot(environments=[env], containers=[container]))
    state = AppState(
        settings_repo=repo,
        mapping_repo=mapping_repo,
        snapshot_use_case=use_case,
    )

    asyncio.run(state.load_mappings_page())

    assert list(state.containers) == [container]
    assert list(state.mappings) == [
        {"container_name": "web", "channel_id": "ch-1", "enabled": True}
    ]


def test_load_mappings_page_missing_config_does_not_request() -> None:
    repo = FakeSettingsRepository()
    use_case = FakeSnapshotUseCase()
    state = AppState(settings_repo=repo, snapshot_use_case=use_case)

    asyncio.run(state.load_mappings_page())

    assert "Configure Dockhand settings" in state.status_message
    assert not use_case.called


def test_refresh_status_populates_lists() -> None:
    env = _environment("e1", "prod")
    container = _container("c1", "web", "e1")
    use_case = FakeSnapshotUseCase(Snapshot(environments=[env], containers=[container]))
    state = AppState(snapshot_use_case=use_case)

    asyncio.run(state.refresh_status())

    assert list(state.environments) == [env]
    assert list(state.containers) == [container]
    assert use_case.called
    assert "1 environment(s), 1 container(s)" in state.status_message


def test_refresh_status_reports_failure_without_crashing() -> None:
    state = AppState(snapshot_use_case=FakeSnapshotUseCase(exc=RuntimeError("down")))

    asyncio.run(state.refresh_status())

    assert list(state.environments) == []
    assert list(state.containers) == []
    assert "Failed to refresh status" in state.status_message
    assert "down" in state.status_message
