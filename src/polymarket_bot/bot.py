"""Core bot class with cog loading."""

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from polymarket_bot.config import settings

log = logging.getLogger(__name__)

COGS_DIR = Path(__file__).parent / "cogs"


class PolymarketBot(commands.Bot):
    """Discord bot that auto-loads all cogs in the project package."""

    def __init__(self) -> None:
        """Initialize the bot with default intents and configured guild scope."""
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

        self.guild_id = settings.discord_guild_id

    async def setup_hook(self) -> None:
        """Load cogs and sync slash commands before the bot connects."""
        self.tree.on_error = self._on_tree_error  # type: ignore[assignment]

        for cog_file in COGS_DIR.glob("*.py"):
            if cog_file.name.startswith("_"):
                continue
            ext = f"polymarket_bot.cogs.{cog_file.stem}"
            await self.load_extension(ext)
            log.info("Loaded extension: %s", ext)

        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def _on_tree_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError) -> None:
        """Log slash-command failures and send a fallback error response."""
        original = getattr(error, "original", error)
        if isinstance(original, discord.NotFound) and original.code == 10062:
            log.warning("Interaction expired for /%s (user likely retried)", interaction.command)
            return
        log.exception("Slash command error in /%s", interaction.command, exc_info=error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send("Something went wrong. Please try again.", ephemeral=True)
            else:
                await interaction.response.send_message("Something went wrong. Please try again.", ephemeral=True)
        except discord.HTTPException:
            pass

    async def on_ready(self) -> None:
        """Log a startup message once the bot is fully connected."""
        log.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "?")

    async def on_command_error(self, ctx, error) -> None:
        """Log prefix-command failures reserved for admin or debug usage."""
        log.error("Command error: %s", error)

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        """Log uncaught Discord event handler exceptions."""
        log.exception("Unhandled exception in %s", event_method)
