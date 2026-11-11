"""Tests for RestartContainerUseCase."""

import pytest

from dockhand_discord_control.domain.exceptions import DockhandClientError
from dockhand_discord_control.domain.models import ActionResult, ChannelMapping
from dockhand_discord_control.domain.use_cases import RestartContainerUseCase


class _MappingRepository:
    def __init__(self, mapping: ChannelMapping | None) -> None:
        self._mapping = mapping

    def get_mapping(self, channel_id: str):
        return self._mapping

    def mappings_for_container(self, container_name: str):
        return []


class _RecordingClient:
    """Client that records the order of stop/start calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.stopped: list[str] = []
        self.started: list[str] = []

    def list_environments(self):
        return []

    def list_containers(self, environment_id: str):
        return []

    def start_container(self, container_id: str) -> ActionResult:
        self.calls.append("start")
        self.started.append(container_id)
        return ActionResult(ok=True, message="started")

    def stop_container(self, container_id: str) -> ActionResult:
        self.calls.append("stop")
        self.stopped.append(container_id)
        return ActionResult(ok=True, message="stopped")


class _RejectingStopClient(_RecordingClient):
    """Client whose stop returns a failed result instead of raising."""

    def stop_container(self, container_id: str) -> ActionResult:
        self.calls.append("stop")
        self.stopped.append(container_id)
        return ActionResult(ok=False, message="container not running")


class _RejectingStartClient(_RecordingClient):
    """Client whose start returns a failed result instead of raising."""

    def start_container(self, container_id: str) -> ActionResult:
        self.calls.append("start")
        self.started.append(container_id)
        return ActionResult(ok=False, message="start rejected by server")


class _RaisingStopClient(_RecordingClient):
    def stop_container(self, container_id: str) -> ActionResult:
        raise DockhandClientError("stop rejected")


class _RaisingStartClient(_RecordingClient):
    def start_container(self, container_id: str) -> ActionResult:
        raise DockhandClientError("start rejected")


def _mapping(enabled: bool = True, container_name: str = "web") -> ChannelMapping:
    return ChannelMapping(
        container_name=container_name, channel_id="ch1", enabled=enabled
    )


def test_execute_stops_then_starts_container_for_authorized_channel() -> None:
    client = _RecordingClient()
    use_case = RestartContainerUseCase(client, _MappingRepository(_mapping()))

    result = use_case.execute("ch1", "web")

    assert result.ok is True
    assert client.calls == ["stop", "start"]
    assert client.stopped == ["web"]
    assert client.started == ["web"]
    assert "stopped then started container web" in result.message


@pytest.mark.parametrize(
    "mapping,channel_id,container_name",
    [
        (None, "ch1", "web"),  # not found
        (_mapping(enabled=False), "ch1", "web"),  # disabled
        (_mapping(container_name="api"), "ch1", "web"),  # wrong container
    ],
)
def test_execute_rejects_unauthorized_or_missing_mapping(
    mapping: ChannelMapping | None, channel_id: str, container_name: str
) -> None:
    client = _RecordingClient()
    use_case = RestartContainerUseCase(client, _MappingRepository(mapping))

    result = use_case.execute(channel_id, container_name)

    assert result.ok is False
    assert result.message
    assert client.calls == []


def test_execute_skips_start_when_stop_fails() -> None:
    client = _RejectingStopClient()
    use_case = RestartContainerUseCase(client, _MappingRepository(_mapping()))

    result = use_case.execute("ch1", "web")

    assert result.ok is False
    assert client.calls == ["stop"]
    assert client.started == []
    assert "stop" in result.message


def test_execute_reports_start_failure_after_successful_stop() -> None:
    client = _RejectingStartClient()
    use_case = RestartContainerUseCase(client, _MappingRepository(_mapping()))

    result = use_case.execute("ch1", "web")

    assert result.ok is False
    assert client.calls == ["stop", "start"]
    assert "start" in result.message


def test_execute_maps_stop_client_error_to_failed_action_result() -> None:
    client = _RaisingStopClient()
    use_case = RestartContainerUseCase(client, _MappingRepository(_mapping()))

    result = use_case.execute("ch1", "web")

    assert result.ok is False
    assert "stop rejected" in result.message
    assert client.started == []


def test_execute_maps_start_client_error_to_failed_action_result() -> None:
    client = _RaisingStartClient()
    use_case = RestartContainerUseCase(client, _MappingRepository(_mapping()))

    result = use_case.execute("ch1", "web")

    assert result.ok is False
    assert "start rejected" in result.message
    assert client.stopped == ["web"]
