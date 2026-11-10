"""Tests for :mod:`dockhand_discord_control.discord.rendering`."""

from dockhand_discord_control.discord import rendering
from dockhand_discord_control.domain.models import (
    ActionResult,
    ContainerStatus,
    DockerContainer,
    DockhandEnvironment,
    EnvironmentStatus,
    Snapshot,
)


def _environment(
    environment_id: str = "e1",
    name: str = "production",
    status: EnvironmentStatus = EnvironmentStatus.RUNNING,
) -> DockhandEnvironment:
    return DockhandEnvironment(
        id=environment_id,
        name=name,
        status=status,
        base_url="http://dockhand:8080",
    )


def _container(
    container_id: str = "c1",
    name: str = "web",
    image: str = "nginx:latest",
    status: ContainerStatus = ContainerStatus.RUNNING,
    environment_id: str = "e1",
) -> DockerContainer:
    return DockerContainer(
        id=container_id,
        name=name,
        image=image,
        status=status,
        environment_id=environment_id,
    )


def test_render_snapshot_with_environments_and_containers() -> None:
    snapshot = Snapshot(
        environments=[_environment()],
        containers=[
            _container(),
            _container(
                container_id="c2",
                name="api",
                image="api:1",
                status=ContainerStatus.STOPPED,
            ),
        ],
    )

    reply = rendering.render_snapshot(snapshot)

    assert "Dockhand status:" in reply
    assert "production (e1): running" in reply
    assert "- web (c1): running [nginx:latest]" in reply
    assert "- api (c2): stopped [api:1]" in reply


def test_render_snapshot_without_environments() -> None:
    reply = rendering.render_snapshot(Snapshot(environments=[], containers=[]))

    assert reply == "Dockhand status:\nNo environments found."


def test_render_snapshot_environment_without_containers() -> None:
    snapshot = Snapshot(environments=[_environment()], containers=[])

    reply = rendering.render_snapshot(snapshot)

    assert "production (e1): running" in reply
    assert "  (no containers)" in reply


def test_render_container_list() -> None:
    reply = rendering.render_container_list(
        [
            _container(),
            _container(
                container_id="c2",
                name="api",
                image="api:1",
                status=ContainerStatus.STOPPED,
            ),
        ]
    )

    assert "Containers:" in reply
    assert "- web (c1): running — nginx:latest (environment e1)" in reply
    assert "- api (c2): stopped — api:1 (environment e1)" in reply


def test_render_container_list_empty() -> None:
    assert rendering.render_container_list([]) == "No containers found."


def test_render_action_result_ok() -> None:
    assert (
        rendering.render_action_result(
            ActionResult(ok=True, message="started"), "start"
        )
        == "Start succeeded: started"
    )


def test_render_action_result_failed() -> None:
    assert (
        rendering.render_action_result(
            ActionResult(ok=False, message="rejected"), "stop"
        )
        == "Stop failed: rejected"
    )
