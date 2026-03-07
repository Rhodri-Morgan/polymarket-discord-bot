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
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

        self.guild_id = settings.discord_guild_id

    async def setup_hook(self) -> None:
        for cog_file in COGS_DIR.glob("*.py"):
            if cog_file.name.startswith("_"):
                continue
            ext = f"polymarket_bot.cogs.{cog_file.stem}"
            await self.load_extension(ext)
            log.info("Loaded extension: %s", ext)

        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "?")
