"""Polymarket cog — slash commands for querying Polymarket data."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from polymarket_bot.formatting import format_market_list, total_pages
from polymarket_bot.views import MarketPaginationView

if TYPE_CHECKING:
    from polymarket_bot.bot import PolymarketBot

log = logging.getLogger(__name__)

PER_PAGE = 5


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

    async def _fetch_markets(self, tag_slug: str = "", limit: int = 50) -> list[dict]:
        """Fetch markets, optionally filtered by tag via the events endpoint."""
        if not self.session:
            return []

        if tag_slug:
            return await self._fetch_markets_by_tag(tag_slug, limit)

        url = f"{self.gamma_url}/markets"
        params = {"limit": limit, "active": "true", "closed": "false"}
        async with self.session.get(url, params=params) as resp:
            if resp.status != 200:
                log.warning("Gamma API /markets returned %s", resp.status)
                return []
            return await resp.json()

    async def _fetch_markets_by_tag(self, tag_slug: str, limit: int = 50) -> list[dict]:
        """Fetch markets via the events endpoint filtered by tag_slug."""
        if not self.session:
            return []

        url = f"{self.gamma_url}/events"
        params = {
            "tag_slug": tag_slug.lower(),
            "active": "true",
            "closed": "false",
            "limit": 20,
        }
        async with self.session.get(url, params=params) as resp:
            if resp.status != 200:
                log.warning("Gamma API /events returned %s", resp.status)
                return []
            events = await resp.json()

        # Flatten markets from events, carrying event tags into each market
        markets: list[dict] = []
        for event in events:
            event_tags = [t.get("label", "") for t in event.get("tags", [])]
            for market in event.get("markets", []):
                market["_event_tags"] = event_tags
                if "events" not in market:
                    market["events"] = [{"slug": event.get("slug", "")}]
                markets.append(market)
        return markets[:limit]

    @app_commands.command(name="markets", description="Browse active Polymarket markets")
    @app_commands.describe(
        tag="Filter by category (e.g. sports, politics, crypto, finance)",
    )
    async def markets_cmd(self, interaction: discord.Interaction, tag: str = "") -> None:
        await interaction.response.defer()
        markets = await self._fetch_markets(tag)
        if not markets:
            await interaction.followup.send("No markets found.")
            return

        embeds = format_market_list(markets, page=0, per_page=PER_PAGE)
        num_pages = total_pages(len(markets), PER_PAGE)

        kwargs: dict = {"embeds": embeds}
        if num_pages > 1:
            kwargs["view"] = MarketPaginationView(markets, per_page=PER_PAGE)
        await interaction.followup.send(**kwargs)

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping_cmd(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! ({latency}ms)")


async def setup(bot: PolymarketBot) -> None:
    await bot.add_cog(PolymarketCog(bot))
