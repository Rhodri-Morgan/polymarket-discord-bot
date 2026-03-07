"""New Market Alerts cog — hourly check for newly listed Polymarket markets."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from polymarket_bot import market_url, store
from polymarket_bot.formatting import format_market_embed, format_market_list, total_pages
from polymarket_bot.views import MarketPaginationView

if TYPE_CHECKING:
    from polymarket_bot.bot import PolymarketBot

log = logging.getLogger(__name__)

GAMMA_PAGE_LIMIT = 100


async def _fetch_active_markets(session: aiohttp.ClientSession, gamma_url: str) -> list[dict]:
    """Fetch all active, non-closed markets from the Gamma API (paginated)."""
    all_markets: list[dict] = []
    offset = 0
    while True:
        url = f"{gamma_url}/markets"
        params = {
            "active": "true",
            "closed": "false",
            "limit": GAMMA_PAGE_LIMIT,
            "offset": offset,
        }
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                log.warning("Gamma API /markets returned %s", resp.status)
                break
            page = await resp.json()
        if not page:
            break
        all_markets.extend(page)
        if len(page) < GAMMA_PAGE_LIMIT:
            break
        offset += GAMMA_PAGE_LIMIT
    return all_markets


async def check_new_markets(
    session: aiohttp.ClientSession,
    gamma_url: str,
) -> list[dict]:
    """Core logic for the new-market check.

    Returns a list of new market dicts, or an empty list on cold start.
    Handles state loading, diffing, pruning, and saving via store.py.
    """
    markets = await _fetch_active_markets(session, gamma_url)
    active_ids = {m["id"] for m in markets}
    active_by_id = {m["id"]: m for m in markets}

    state = await store.load("seen_markets")
    seen_ids = set(state.get("seen_ids", []))

    is_cold_start = not state  # empty dict → first run

    # Diff: find IDs we haven't seen before
    new_ids = active_ids - seen_ids
    new_markets = [active_by_id[mid] for mid in new_ids]

    # Prune: only keep IDs that are still active
    updated_ids = (seen_ids | new_ids) & active_ids

    await store.save(
        "seen_markets",
        {
            "seen_ids": sorted(updated_ids),
            "last_check": datetime.now(timezone.utc).isoformat(),
        },
    )

    if is_cold_start:
        log.info("Cold start: seeded %d market IDs, posting nothing.", len(updated_ids))
        return []

    if new_markets:
        log.info("Found %d new market(s).", len(new_markets))
    return new_markets


class NewMarketsCog(commands.Cog, name="NewMarkets"):
    """Hourly alerts for newly listed Polymarket markets."""

    def __init__(self, bot: PolymarketBot) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        from polymarket_bot.config import settings

        self.gamma_url = settings.gamma_api_url
        self.alert_channel_id = settings.alert_channel_id
        self.session = aiohttp.ClientSession()
        self.check_loop.start()

    async def cog_unload(self) -> None:
        self.check_loop.cancel()
        if self.session:
            await self.session.close()

    @tasks.loop(hours=1)
    async def check_loop(self) -> None:
        await self._run_check()

    @check_loop.before_loop
    async def before_check_loop(self) -> None:
        await self.bot.wait_until_ready()

    async def _run_check(self) -> None:
        if not self.session or not self.alert_channel_id:
            return

        channel = self.bot.get_channel(self.alert_channel_id)
        if channel is None:
            log.warning("Alert channel %s not found.", self.alert_channel_id)
            return

        new_markets = await check_new_markets(self.session, self.gamma_url)
        if not new_markets:
            return

        # Send each new market as a rich embed
        for market in new_markets:
            embed = format_market_embed(market)
            embed.title = f"🆕 {market.get('question', 'New Market')}"
            embed.colour = discord.Colour.green()
            await channel.send(embed=embed)

    @app_commands.command(name="new-markets", description="Manually check for new Polymarket markets")
    async def new_markets_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if not self.session:
            await interaction.followup.send("Session not ready.")
            return

        new_markets = await check_new_markets(self.session, self.gamma_url)
        if not new_markets:
            await interaction.followup.send("No new markets found since last check.")
            return

        per_page = 5
        title = f"🆕 New Markets ({len(new_markets)} found)"
        colour = discord.Colour.green()

        embeds = format_market_list(new_markets, page=0, per_page=per_page)
        embeds[0].title = title
        embeds[0].colour = colour

        kwargs: dict = {"embeds": embeds}
        if total_pages(len(new_markets), per_page) > 1:
            kwargs["view"] = MarketPaginationView(new_markets, per_page=per_page, title=title, colour=colour)
        await interaction.followup.send(**kwargs)


async def setup(bot: PolymarketBot) -> None:
    await bot.add_cog(NewMarketsCog(bot))
