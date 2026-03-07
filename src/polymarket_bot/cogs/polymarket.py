"""Polymarket cog — slash commands for querying Polymarket data."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from polymarket_bot import market_url

if TYPE_CHECKING:
    from polymarket_bot.bot import PolymarketBot

log = logging.getLogger(__name__)


class PolymarketCog(commands.Cog, name="Polymarket"):
    """Query live Polymarket prediction-market data."""

    def __init__(self, bot: PolymarketBot) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        from polymarket_bot.config import settings

        self.gamma_url = settings.gamma_api_url
        self.session = aiohttp.ClientSession()

    async def cog_unload(self) -> None:
        if self.session:
            await self.session.close()

    async def _fetch_markets(self, tag: str = "", limit: int = 5) -> list[dict]:
        if not self.session:
            return []
        url = f"{self.gamma_url}/markets"
        params = {"limit": limit, "active": "true", "closed": "false"}
        if tag:
            params["tag"] = tag
        async with self.session.get(url, params=params) as resp:
            if resp.status != 200:
                log.warning("Gamma API /markets returned %s", resp.status)
                return []
            return await resp.json()

    @app_commands.command(name="markets", description="List active Polymarket markets")
    @app_commands.describe(tag="Filter markets by tag (e.g. politics, crypto, sports)")
    async def markets_cmd(self, interaction: discord.Interaction, tag: str = "") -> None:
        await interaction.response.defer()
        markets = await self._fetch_markets(tag)
        if not markets:
            await interaction.followup.send("No markets found.")
            return

        embed = discord.Embed(title="Polymarket — Active Markets", colour=discord.Colour.blue())
        for market in markets[:5]:
            question = market.get("question", "Unknown")
            volume = market.get("volume", "N/A")
            link = market_url(market)
            value = f"Volume: ${volume}"
            if link:
                value += f"  |  [View]({link})"
            embed.add_field(
                name=question,
                value=value,
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping_cmd(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! ({latency}ms)")


async def setup(bot: PolymarketBot) -> None:
    await bot.add_cog(PolymarketCog(bot))
