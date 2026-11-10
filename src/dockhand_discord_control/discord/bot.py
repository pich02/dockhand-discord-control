"""Thin :mod:`discord.ext.commands.Bot` exposing /dockhand_* slash commands.

The :mod:`discord.py` import is guarded so this module can be imported (and
lightly tested) in environments without it. The pure-Python command logic
lives in :mod:`dockhand_discord_control.discord.commands`; this layer only
translates Discord interactions into handler calls and sends back replies.
"""

from __future__ import annotations

from typing import Any

from dockhand_discord_control.discord.commands import DiscordCommandHandlers

try:
    import discord as _discord
    from discord.ext import commands as _ext_commands
except ImportError:  # pragma: no cover - environments without discord.py installed
    _discord = None  # type: ignore[assignment]
    _ext_commands = None  # type: ignore[assignment]

DiscordBot: Any  # real commands.Bot subclass when discord.py is installed


class _DiscordBotPlaceholder:
    """Placeholder when :mod:`discord.py` is not installed."""

    _token: str
    _handlers: DiscordCommandHandlers
    _guild_id: str | None
    tree: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "discord.py is required to run DiscordBot; install the "
            "discord.py package to run the Discord adapter"
        )

    def register_commands(self) -> None:
        raise NotImplementedError("discord.py is required")

    def run(self) -> None:
        raise NotImplementedError("discord.py is required")


if _discord is not None and _ext_commands is not None:
    # Aliases bound under the guard above; their types are narrowed so the
    # class below can reference discord.py without "None" errors.
    _Discord = _discord
    _Commands = _ext_commands

    class _DiscordBotImpl(_Commands.Bot):
        """A :class:`discord.ext.commands.Bot` with /dockhand_* slash commands.

        ``token`` is the Discord bot token and ``handlers`` owns the pure
        Python command logic. ``guild_id`` optionally scopes slash-command
        registration to a single guild.
        """

        _token: str
        _handlers: DiscordCommandHandlers
        _guild_id: str | None

        def __init__(
            self,
            *,
            token: str,
            handlers: DiscordCommandHandlers,
            guild_id: str | int | None = None,
        ) -> None:
            super().__init__(
                command_prefix="!",
                intents=_Discord.Intents.default(),
            )
            self._token = token
            self._handlers = handlers
            self._guild_id = str(guild_id) if guild_id is not None else None

        def register_commands(self) -> None:
            """Register the /dockhand_* slash commands on the command tree."""
            tree = self.tree

            @tree.command(
                name="dockhand_status",
                description=("Show the status of Dockhand environments and containers"),
            )
            async def dockhand_status(interaction: _Discord.Interaction) -> None:
                await interaction.response.defer(ephemeral=True)
                channel_id = (
                    str(interaction.channel_id)
                    if interaction.channel_id is not None
                    else ""
                )
                reply = self._handlers.handle_status(interaction, channel_id)
                await interaction.followup.send(reply, ephemeral=True)

            @tree.command(
                name="dockhand_list",
                description="List all containers known to Dockhand",
            )
            async def dockhand_list(interaction: _Discord.Interaction) -> None:
                await interaction.response.defer(ephemeral=True)
                channel_id = (
                    str(interaction.channel_id)
                    if interaction.channel_id is not None
                    else ""
                )
                reply = self._handlers.handle_list(interaction, channel_id)
                await interaction.followup.send(reply, ephemeral=True)

            @tree.command(
                name="dockhand_start",
                description="Start a container this channel is authorized for",
            )
            async def dockhand_start(
                interaction: _Discord.Interaction, container: str
            ) -> None:
                await interaction.response.defer(ephemeral=True)
                channel_id = (
                    str(interaction.channel_id)
                    if interaction.channel_id is not None
                    else ""
                )
                reply = self._handlers.handle_start(interaction, channel_id, container)
                await interaction.followup.send(reply, ephemeral=True)

            @tree.command(
                name="dockhand_stop",
                description="Stop a container this channel is authorized for",
            )
            async def dockhand_stop(
                interaction: _Discord.Interaction, container: str
            ) -> None:
                await interaction.response.defer(ephemeral=True)
                channel_id = (
                    str(interaction.channel_id)
                    if interaction.channel_id is not None
                    else ""
                )
                reply = self._handlers.handle_stop(interaction, channel_id, container)
                await interaction.followup.send(reply, ephemeral=True)

            @tree.command(
                name="dockhand_restart",
                description="Restart a container this channel is authorized for",
            )
            async def dockhand_restart(
                interaction: _Discord.Interaction, container: str
            ) -> None:
                await interaction.response.defer(ephemeral=True)
                channel_id = (
                    str(interaction.channel_id)
                    if interaction.channel_id is not None
                    else ""
                )
                reply = self._handlers.handle_restart(
                    interaction, channel_id, container
                )
                await interaction.followup.send(reply, ephemeral=True)

        async def setup_hook(self) -> None:
            self.register_commands()
            # TODO: slash-command registration strategy is an open item.
            # When DISCORD_GUILD_ID is set, sync guild-scoped so command
            # updates appear instantly; otherwise sync globally (global
            # commands can take up to an hour to propagate to all guilds).
            if self._guild_id is not None:
                guild = _Discord.Object(id=int(self._guild_id))
                tree = self.tree
                tree.copy_global_to(guild=guild)
                await tree.sync(guild=guild)
            else:
                await self.tree.sync()

        def run(self) -> None:
            """Start the bot with the configured Discord bot token."""
            super().run(self._token)

    DiscordBot: Any = _DiscordBotImpl

else:
    DiscordBot = _DiscordBotPlaceholder
