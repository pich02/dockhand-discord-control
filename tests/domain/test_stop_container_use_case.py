"""Tests for StopContainerUseCase."""

import pytest

from dockhand_discord_control.domain.exceptions import DockhandClientError
from dockhand_discord_control.domain.models import ActionResult, ChannelMapping
from dockhand_discord_control.domain.use_cases import StopContainerUseCase


class _MappingRepository:
    def __init__(self, mapping: ChannelMapping | None) -> None:
        self._mapping = mapping

    def get_mapping(self, channel_id: str):
        return self._mapping

    def mappings_for_container(self, container_name: str):
        return []


class _AuthorizedClient:
    def __init__(self) -> None:
        self.stopped: list[str] = []

    def list_environments(self):
        return []

    def list_containers(self, environment_id: str):
        return []

    def start_container(self, container_id: str) -> ActionResult:
        return ActionResult(ok=True, message="started")

    def stop_container(self, container_id: str) -> ActionResult:
        self.stopped.append(container_id)
        return ActionResult(ok=True, message="stopped")


class _FailingClient:
    def list_environments(self):
        return []

    def list_containers(self, environment_id: str):
        return []

    def start_container(self, container_id: str) -> ActionResult:
        raise DockhandClientError("start rejected")

    def stop_container(self, container_id: str) -> ActionResult:
        raise DockhandClientError("stop rejected")


def test_execute_stops_container_for_authorized_channel() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    client = _AuthorizedClient()
    use_case = StopContainerUseCase(client, _MappingRepository(mapping))

    result = use_case.execute("ch1", "web")

    assert result.ok is True
    assert result.message == "stopped"
    assert client.stopped == ["web"]


@pytest.mark.parametrize(
    "mapping,channel_id,container_name",
    [
        (None, "ch1", "web"),  # not found
        (
            ChannelMapping(container_name="web", channel_id="ch1", enabled=False),
            "ch1",
            "web",
        ),  # disabled
        (
            ChannelMapping(container_name="api", channel_id="ch1", enabled=True),
            "ch1",
            "web",
        ),  # wrong container
    ],
)
def test_execute_rejects_unauthorized_or_missing_mapping(
    mapping: ChannelMapping | None, channel_id: str, container_name: str
) -> None:
    client = _AuthorizedClient()
    use_case = StopContainerUseCase(client, _MappingRepository(mapping))

    result = use_case.execute(channel_id, container_name)

    assert result.ok is False
    assert result.message
    assert client.stopped == []


def test_execute_maps_client_error_to_failed_action_result() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1", enabled=True)
    use_case = StopContainerUseCase(_FailingClient(), _MappingRepository(mapping))

    result = use_case.execute("ch1", "web")

    assert result.ok is False
    assert "stop rejected" in result.message
