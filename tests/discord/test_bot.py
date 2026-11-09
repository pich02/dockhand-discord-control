"""Light tests for :class:`DiscordBot` without a live Discord connection."""

import asyncio
from typing import Any

from discord import app_commands

from dockhand_discord_control.discord.bot import DiscordBot
from dockhand_discord_control.discord.commands import DiscordCommandHandlers
from dockhand_discord_control.domain.models import (
    ActionResult,
    ChannelMapping,
)
from dockhand_discord_control.domain.use_cases import (
    SnapshotUseCase,
    StartContainerUseCase,
    StopContainerUseCase,
)


class _Client:
    """Fake for the DockhandClient port used by the bot tests."""

    def list_environments(self) -> list:
        return []

    def list_containers(self, environment_id: str) -> list:
        return []

    def start_container(self, container_id: str) -> ActionResult:
        return ActionResult(ok=True, message="started")

    def stop_container(self, container_id: str) -> ActionResult:
        return ActionResult(ok=True, message="stopped")


class _Repo:
    """Fake mapping repository: channel 123 is enabled for container web."""

    def get_mapping(self, channel_id: str) -> ChannelMapping | None:
        if channel_id == "123":
            return ChannelMapping(container_name="web", channel_id="123", enabled=True)
        return None

    def mappings_for_container(self, container_name: str) -> list[ChannelMapping]:
        return []


def _make_handlers() -> DiscordCommandHandlers:
    client = _Client()
    repo = _Repo()
    return DiscordCommandHandlers(
        snapshot_use_case=SnapshotUseCase(client),
        start_use_case=StartContainerUseCase(client, repo),
        stop_use_case=StopContainerUseCase(client, repo),
        mapping_repo=repo,
    )


def _make_bot() -> Any:
    return DiscordBot(token="test-token", handlers=_make_handlers())


def test_bot_stores_token_and_handlers_without_connecting() -> None:
    bot = _make_bot()

    assert bot._token == "test-token"
    assert isinstance(bot._handlers, DiscordCommandHandlers)


def test_register_commands_registers_all_four_slash_commands() -> None:
    bot = _make_bot()
    bot.register_commands()

    assert bot.tree.get_command("dockhand_status") is not None
    assert bot.tree.get_command("dockhand_list") is not None
    assert bot.tree.get_command("dockhand_start") is not None
    assert bot.tree.get_command("dockhand_stop") is not None


class _FakeResponse:
    def __init__(self) -> None:
        self.deferred: bool | None = None

    async def defer(self, *, ephemeral: bool) -> None:
        self.deferred = ephemeral


class _FakeFollowup:
    def __init__(self) -> None:
        self.sent: str | None = None
        self.ephemeral: bool | None = None

    async def send(self, content: str, *, ephemeral: bool) -> None:
        self.sent = content
        self.ephemeral = ephemeral


class _FakeInteraction:
    def __init__(self, channel_id: int) -> None:
        self.channel_id = channel_id
        self.response = _FakeResponse()
        self.followup = _FakeFollowup()


_START_STOP_CASES = (
    ("dockhand_start", "web", "Start succeeded: started"),
    ("dockhand_stop", "web", "Stop succeeded: stopped"),
)


def test_start_and_stop_delegate_to_handlers_and_reply_ephemerally() -> None:
    bot = _make_bot()
    bot.register_commands()

    for command_name, container, expected_reply in _START_STOP_CASES:
        command = bot.tree.get_command(command_name)
        assert isinstance(command, app_commands.Command)

        interaction = _FakeInteraction(channel_id=123)
        callback: Any = command.callback
        asyncio.run(callback(interaction, container))

        assert interaction.response.deferred is True
        sent = interaction.followup.sent
        assert sent is not None
        assert sent == expected_reply
        assert interaction.followup.ephemeral is True


def test_status_and_list_reply_ephemerally() -> None:
    bot = _make_bot()
    bot.register_commands()

    for command_name in ("dockhand_status", "dockhand_list"):
        command = bot.tree.get_command(command_name)
        assert isinstance(command, app_commands.Command)

        interaction = _FakeInteraction(channel_id=123)
        callback: Any = command.callback
        asyncio.run(callback(interaction))

        assert interaction.response.deferred is True
        assert interaction.followup.ephemeral is True
        sent = interaction.followup.sent
        assert sent is not None
        if command_name == "dockhand_status":
            assert "Dockhand status" in sent
        else:
            assert "Containers" in sent or "No containers found." in sent


def test_unauthorized_channel_replies_not_authorized() -> None:
    bot = _make_bot()
    bot.register_commands()

    interaction = _FakeInteraction(channel_id=999)  # no mapping for this channel
    command = bot.tree.get_command("dockhand_start")
    assert isinstance(command, app_commands.Command)
    callback: Any = command.callback
    asyncio.run(callback(interaction, "web"))

    assert interaction.followup.ephemeral is True
    sent = interaction.followup.sent
    assert sent is not None
    assert "not authorized" in sent.lower()
