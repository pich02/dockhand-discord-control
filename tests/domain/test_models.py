"""Tests for the domain models."""

import pytest
from pydantic import ValidationError

from dockhand_discord_control.domain.models import (
    ActionResult,
    ChannelMapping,
    ContainerStatus,
    DockerContainer,
    DockhandEnvironment,
    EnvironmentStatus,
    Snapshot,
)


def test_container_status_enum_values() -> None:
    assert ContainerStatus.RUNNING == "running"
    assert ContainerStatus.STOPPED == "stopped"
    assert ContainerStatus.UNKNOWN == "unknown"


def test_docker_container_is_frozen() -> None:
    container = DockerContainer(
        id="c1",
        name="web",
        image="nginx:latest",
        status=ContainerStatus.RUNNING,
        environment_id="e1",
    )
    with pytest.raises(ValidationError):
        container.name = "other"


def test_docker_container_coerces_status_str() -> None:
    container = DockerContainer(
        id="c1",
        name="web",
        image="nginx:latest",
        status=ContainerStatus("running"),
        environment_id="e1",
    )
    assert container.status is ContainerStatus.RUNNING


def test_snapshot_assembles_environments_and_containers() -> None:
    env = DockhandEnvironment(
        id="e1",
        name="prod",
        status=EnvironmentStatus.RUNNING,
        base_url="http://localhost:8000",
    )
    container = DockerContainer(
        id="c1",
        name="web",
        image="nginx:latest",
        status=ContainerStatus.STOPPED,
        environment_id="e1",
    )
    snapshot = Snapshot(environments=[env], containers=[container])
    assert snapshot.environments == [env]
    assert snapshot.containers == [container]


def test_action_result_defaults_payload() -> None:
    result = ActionResult(ok=True, message="done")
    assert result.payload is None


def test_channel_mapping_defaults_enabled() -> None:
    mapping = ChannelMapping(container_name="web", channel_id="ch1")
    assert mapping.enabled is True
