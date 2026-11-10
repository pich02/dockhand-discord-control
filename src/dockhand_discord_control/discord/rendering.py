"""Pure reply rendering for the Discord adapter.

Formats domain models into user-facing plain-text replies. These functions
have no dependency on :mod:`discord.py` or the Dockhand API, so they are
straightforward to unit test in isolation.
"""

from __future__ import annotations

from dockhand_discord_control.domain.models import (
    ActionResult,
    DockerContainer,
    Snapshot,
)


def render_snapshot(snapshot: Snapshot) -> str:
    """Render a :class:`Snapshot` as a status reply."""
    lines: list[str] = ["Dockhand status:"]
    if not snapshot.environments:
        lines.append("No environments found.")
        return "\n".join(lines)

    containers_by_environment: dict[str, list[DockerContainer]] = {}
    for container in snapshot.containers:
        containers_by_environment.setdefault(container.environment_id, []).append(
            container
        )

    for environment in snapshot.environments:
        lines.append(
            f"- {environment.name} ({environment.id}): {environment.status.value}"
        )
        environment_containers = containers_by_environment.get(environment.id, [])
        if not environment_containers:
            lines.append("  (no containers)")
            continue
        for container in environment_containers:
            lines.append(
                f"  - {container.name} ({container.id}): {container.status.value} "
                f"[{container.image}]"
            )
    return "\n".join(lines)


def render_container_list(containers: list[DockerContainer]) -> str:
    """Render a list of containers."""
    if not containers:
        return "No containers found."
    lines: list[str] = ["Containers:"]
    for container in containers:
        lines.append(
            f"- {container.name} ({container.id}): {container.status.value} — "
            f"{container.image} (environment {container.environment_id})"
        )
    return "\n".join(lines)


def render_action_result(result: ActionResult, action: str) -> str:
    """Render an :class:`ActionResult` as a user-facing reply."""
    if result.ok:
        return f"{action.capitalize()} succeeded: {result.message}"
    return f"{action.capitalize()} failed: {result.message}"
