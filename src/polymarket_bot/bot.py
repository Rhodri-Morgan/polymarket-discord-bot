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
        """Initialize the bot with default intents."""
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

        self._guild_cleanup_done = False

    async def setup_hook(self) -> None:
        """Load cogs and sync slash commands globally before the bot connects."""
        self.tree.on_error = self._on_tree_error  # type: ignore[assignment]

        for cog_file in COGS_DIR.glob("*.py"):
            if cog_file.name.startswith("_"):
                continue
            ext = f"polymarket_bot.cogs.{cog_file.stem}"
            await self.load_extension(ext)
            log.info("Loaded extension: %s", ext)

        await self.tree.sync()
        log.info("Synced slash commands globally")

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
        """Log a startup message, clear stale guild-scoped commands, set rich presence."""
        if not self._guild_cleanup_done:
            for guild in self.guilds:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
            if self.guilds:
                log.info("Cleared guild-scoped commands from %d guild(s)", len(self.guilds))
            self._guild_cleanup_done = True

        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Polymarket API"))
        log.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "?")

    async def on_command_error(self, ctx, error) -> None:
        """Log prefix-command failures reserved for admin or debug usage."""
        log.error("Command error: %s", error)

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        """Log uncaught Discord event handler exceptions."""
        log.exception("Unhandled exception in %s", event_method)
