"""Commands cog — lists available slash commands. DM-only."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from polymarket_bot.bot import PolymarketBot

log = logging.getLogger(__name__)


COMMANDS_HELP: list[tuple[str, str]] = [
    ("/commands", "Show this list of available commands (DM-only)."),
    ("/trending", "Top trending Polymarket events from the last 48 hours."),
    ("/mispriced", "Find mispriced Polymarket events with arbitrage opportunities."),
]


def _build_help_embed() -> discord.Embed:
    """Build the embed listing every available bot command."""
    embed = discord.Embed(
        title="Polymarket Discord Bot — Commands",
        description="`/commands` runs in a DM with the bot. `/trending` and `/mispriced` run in a server channel.",
        colour=discord.Colour.purple(),
    )
    for name, description in COMMANDS_HELP:
        embed.add_field(name=name, value=description, inline=False)
    return embed


class CommandsCog(commands.Cog, name="Commands"):
    """Lightweight cog that lists every available bot command in a DM."""

    def __init__(self, bot: PolymarketBot) -> None:
        """Store the bot reference."""
        self.bot = bot

    @app_commands.command(name="commands", description="List available bot commands")
    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def commands_cmd(self, interaction: discord.Interaction) -> None:
        """Reply with the help embed listing every command."""
        await interaction.response.send_message(embed=_build_help_embed())


async def setup(bot: PolymarketBot) -> None:
    """Register the commands cog with the bot."""
    await bot.add_cog(CommandsCog(bot))
