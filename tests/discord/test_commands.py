"""Tests for DiscordCommandHandlers with fakes for the domain ports.

No :mod:`discord.py` and no live Discord connection are involved.
"""

import types

import pytest

from dockhand_discord_control.discord.commands import DiscordCommandHandlers
from dockhand_discord_control.domain.exceptions import DockhandClientError
from dockhand_discord_control.domain.models import (
    ActionResult,
    ChannelMapping,
    ContainerStatus,
    DockerContainer,
    DockhandEnvironment,
    EnvironmentStatus,
)
from dockhand_discord_control.domain.use_cases import (
    RestartContainerUseCase,
    SnapshotUseCase,
    StartContainerUseCase,
    StopContainerUseCase,
)

_INTERACTION = types.SimpleNamespace()


class _FakeDockhandClient:
    """Fake for the DockhandClient port: records calls, optionally fails."""

    def __init__(
        self,
        *,
        environments: list[DockhandEnvironment] | None = None,
        containers_by_environment: dict[str, list[DockerContainer]] | None = None,
        fail_start: bool = False,
        fail_stop: bool = False,
        reject_start: bool = False,
        reject_stop: bool = False,
    ) -> None:
        self.environments = list(environments or [])
        self.containers_by_environment = dict(containers_by_environment or {})
        self.fail_start = fail_start
        self.fail_stop = fail_stop
        self.reject_start = reject_start
        self.reject_stop = reject_stop
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.calls: list[str] = []

    def list_environments(self) -> list[DockhandEnvironment]:
        return list(self.environments)

    def list_containers(self, environment_id: str) -> list[DockerContainer]:
        return list(self.containers_by_environment.get(environment_id, []))

    def start_container(self, container_id: str) -> ActionResult:
        self.started.append(container_id)
        self.calls.append("start")
        if self.fail_start:
            raise DockhandClientError("start rejected")
        if self.reject_start:
            return ActionResult(ok=False, message="start rejected by server")
        return ActionResult(ok=True, message="started")

    def stop_container(self, container_id: str) -> ActionResult:
        self.stopped.append(container_id)
        self.calls.append("stop")
        if self.fail_stop:
            raise DockhandClientError("stop rejected")
        if self.reject_stop:
            return ActionResult(ok=False, message="stop rejected by server")
        return ActionResult(ok=True, message="stopped")


class _FakeMappingRepository:
    """Fake for the ChannelMappingRepository port."""

    def __init__(self, mapping: ChannelMapping | None = None) -> None:
        self._mapping = mapping
        self.looked_up: list[str] = []

    def get_mapping(self, channel_id: str) -> ChannelMapping | None:
        self.looked_up.append(channel_id)
        return self._mapping

    def mappings_for_container(self, container_name: str) -> list[ChannelMapping]:
        return []


def _environments() -> list[DockhandEnvironment]:
    return [
        DockhandEnvironment(
            id="e1",
            name="production",
            status=EnvironmentStatus.RUNNING,
            base_url="http://dockhand:8080",
        ),
        DockhandEnvironment(
            id="e2",
            name="staging",
            status=EnvironmentStatus.STOPPED,
            base_url="http://dockhand:8081",
        ),
    ]


def _containers() -> list[DockerContainer]:
    return [
        DockerContainer(
            id="c1",
            name="web",
            image="nginx:latest",
            status=ContainerStatus.RUNNING,
            environment_id="e1",
        ),
        DockerContainer(
            id="c2",
            name="api",
            image="api:1",
            status=ContainerStatus.STOPPED,
            environment_id="e1",
        ),
    ]


def _make_handlers(
    *,
    mapping: ChannelMapping | None = None,
    fail_start: bool = False,
    fail_stop: bool = False,
    reject_start: bool = False,
    reject_stop: bool = False,
) -> tuple[DiscordCommandHandlers, _FakeDockhandClient, _FakeMappingRepository]:
    client = _FakeDockhandClient(
        environments=_environments(),
        containers_by_environment={"e1": _containers(), "e2": []},
        fail_start=fail_start,
        fail_stop=fail_stop,
        reject_start=reject_start,
        reject_stop=reject_stop,
    )
    repo = _FakeMappingRepository(mapping)
    handlers = DiscordCommandHandlers(
        snapshot_use_case=SnapshotUseCase(client),
        start_use_case=StartContainerUseCase(client, repo),
        stop_use_case=StopContainerUseCase(client, repo),
        restart_use_case=RestartContainerUseCase(client, repo),
        mapping_repo=repo,
    )
    return handlers, client, repo


def test_handle_status_renders_environments_and_containers() -> None:
    handlers, _client, _repo = _make_handlers()

    reply = handlers.handle_status(_INTERACTION, "ch1")

    assert "Dockhand status:" in reply
    assert "production (e1): running" in reply
    assert "staging (e2): stopped" in reply
    assert "- web (c1): running [nginx:latest]" in reply
    assert "- api (c2): stopped [api:1]" in reply


def test_handle_status_reports_no_environments() -> None:
    client = _FakeDockhandClient(environments=[], containers_by_environment={})
    repo = _FakeMappingRepository()
    handlers = DiscordCommandHandlers(
        snapshot_use_case=SnapshotUseCase(client),
        start_use_case=StartContainerUseCase(client, repo),
        stop_use_case=StopContainerUseCase(client, repo),
        restart_use_case=RestartContainerUseCase(client, repo),
        mapping_repo=repo,
    )

    reply = handlers.handle_status(_INTERACTION, "ch1")

    assert reply == "Dockhand status:\nNo environments found."


def test_handle_list_renders_containers() -> None:
    handlers, _client, _repo = _make_handlers()

    reply = handlers.handle_list(_INTERACTION, "ch1")

    assert "Containers:" in reply
    assert "- web (c1): running — nginx:latest (environment e1)" in reply
    assert "- api (c2): stopped — api:1 (environment e1)" in reply


def test_handle_list_reports_no_containers() -> None:
    client = _FakeDockhandClient(environments=[], containers_by_environment={})
    repo = _FakeMappingRepository()
    handlers = DiscordCommandHandlers(
        snapshot_use_case=SnapshotUseCase(client),
        start_use_case=StartContainerUseCase(client, repo),
        stop_use_case=StopContainerUseCase(client, repo),
        restart_use_case=RestartContainerUseCase(client, repo),
        mapping_repo=repo,
    )

    reply = handlers.handle_list(_INTERACTION, "ch1")

    assert reply == "No containers found."


@pytest.mark.parametrize(
    "method_name,mapping,container_name",
    [
        pytest.param("handle_start", None, "web", id="start-no-mapping"),
        pytest.param(
            "handle_start",
            ChannelMapping(container_name="web", channel_id="ch1", enabled=False),
            "web",
            id="start-disabled",
        ),
        pytest.param(
            "handle_start",
            ChannelMapping(container_name="api", channel_id="ch1", enabled=True),
            "web",
            id="start-wrong-container",
        ),
        pytest.param("handle_stop", None, "web", id="stop-no-mapping"),
        pytest.param(
            "handle_stop",
            ChannelMapping(container_name="web", channel_id="ch1", enabled=False),
            "web",
            id="stop-disabled",
        ),
        pytest.param(
            "handle_stop",
            ChannelMapping(container_name="api", channel_id="ch1", enabled=True),
            "web",
            id="stop-wrong-container",
        ),
        pytest.param("handle_restart", None, "web", id="restart-no-mapping"),
        pytest.param(
            "handle_restart",
            ChannelMapping(container_name="web", channel_id="ch1", enabled=False),
            "web",
            id="restart-disabled",
        ),
        pytest.param(
            "handle_restart",
            ChannelMapping(container_name="api", channel_id="ch1", enabled=True),
            "web",
            id="restart-wrong-container",
        ),
    ],
)
def test_handle_start_stop_reject_unauthorized_channels(
    method_name: str, mapping: ChannelMapping | None, container_name: str
) -> None:
    handlers, client, repo = _make_handlers(mapping=mapping)

    reply = getattr(handlers, method_name)(_INTERACTION, "ch1", container_name)

    assert "not authorized" in reply.lower()
    assert client.started == []
    assert client.stopped == []
    assert repo.looked_up == ["ch1"]


def test_handle_start_authorized_container() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    handlers, client, _repo = _make_handlers(mapping=mapping)

    reply = handlers.handle_start(_INTERACTION, "ch1", "web")

    assert client.started == ["web"]
    assert "start succeeded" in reply.lower()
    assert "started" in reply


def test_handle_stop_authorized_container() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    handlers, client, _repo = _make_handlers(mapping=mapping)

    reply = handlers.handle_stop(_INTERACTION, "ch1", "web")

    assert client.stopped == ["web"]
    assert "stop succeeded" in reply.lower()
    assert "stopped" in reply


def test_handle_start_client_error_renders_friendly_reply() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    handlers, client, _repo = _make_handlers(mapping=mapping, fail_start=True)

    reply = handlers.handle_start(_INTERACTION, "ch1", "web")

    assert client.started == ["web"]
    assert "start failed" in reply.lower()
    assert "start rejected" in reply


def test_handle_stop_client_error_renders_friendly_reply() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    handlers, client, _repo = _make_handlers(mapping=mapping, fail_stop=True)

    reply = handlers.handle_stop(_INTERACTION, "ch1", "web")

    assert client.stopped == ["web"]
    assert "stop failed" in reply.lower()
    assert "stop rejected" in reply


def test_handle_restart_stops_then_starts_container() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    handlers, client, _repo = _make_handlers(mapping=mapping)

    reply = handlers.handle_restart(_INTERACTION, "ch1", "web")

    assert client.stopped == ["web"]
    assert client.started == ["web"]
    assert client.calls == ["stop", "start"]
    assert "restart succeeded" in reply.lower()


def test_handle_restart_reports_stop_failure_and_skips_start() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    handlers, client, _repo = _make_handlers(mapping=mapping, reject_stop=True)

    reply = handlers.handle_restart(_INTERACTION, "ch1", "web")

    assert client.stopped == ["web"]
    assert client.started == []
    assert "restart failed" in reply.lower()
    assert "could not stop" in reply.lower()


def test_handle_restart_reports_start_failure_after_successful_stop() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    handlers, client, _repo = _make_handlers(mapping=mapping, reject_start=True)

    reply = handlers.handle_restart(_INTERACTION, "ch1", "web")

    assert client.stopped == ["web"]
    assert client.started == ["web"]
    assert "restart failed" in reply.lower()
    assert "could not start" in reply.lower()


def test_handle_restart_client_error_renders_friendly_reply() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    handlers, client, _repo = _make_handlers(mapping=mapping, fail_stop=True)

    reply = handlers.handle_restart(_INTERACTION, "ch1", "web")

    assert client.stopped == ["web"]
    assert client.started == []
    assert "restart failed" in reply.lower()
    assert "stop rejected" in reply


def test_handle_restart_start_client_error_renders_friendly_reply() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    handlers, client, _repo = _make_handlers(mapping=mapping, fail_start=True)

    reply = handlers.handle_restart(_INTERACTION, "ch1", "web")

    assert client.stopped == ["web"]
    assert client.started == ["web"]
    assert "restart failed" in reply.lower()
    assert "start rejected" in reply
