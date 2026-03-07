"""Opportunity Finder cog — hourly scan for low-liquidity new markets."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from polymarket_bot.formatting import format_market_list, total_pages
from polymarket_bot.views import MarketPaginationView

if TYPE_CHECKING:
    from polymarket_bot.bot import PolymarketBot

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure filtering function
# ---------------------------------------------------------------------------


def _parse_date(market: dict) -> datetime | None:
    """Extract a creation/start date from a market dict, or None if absent."""
    for field in ("startDate", "createdAt", "created_at"):
        raw = market.get(field)
        if raw:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                continue
    return None


def _extract_token_ids(market: dict) -> list[str]:
    """Return the list of CLOB token IDs for a market."""
    clob_token_ids = market.get("clobTokenIds")
    if clob_token_ids:
        if isinstance(clob_token_ids, str):
            try:
                ids = json.loads(clob_token_ids)
            except (json.JSONDecodeError, TypeError):
                ids = []
        else:
            ids = clob_token_ids
        if ids:
            return ids

    tokens = market.get("tokens")
    if tokens:
        if isinstance(tokens, str):
            try:
                tokens = json.loads(tokens)
            except (json.JSONDecodeError, TypeError):
                tokens = []
        if tokens:
            result = []
            for t in tokens:
                tid = t.get("token_id") or t.get("tokenId")
                if tid:
                    result.append(tid)
            return result

    return []


def _get_volume(market: dict) -> float:
    """Extract volume from a market, falling back to liquidityNum if needed."""
    for field in ("volume", "volumeNum", "liquidityNum", "liquidity"):
        val = market.get(field)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return 0.0


def filter_opportunities(
    markets: list[dict],
    spreads: dict[str, float],
    max_volume: float,
    min_spread: float,
    max_age_hours: float = 48,
) -> list[dict]:
    """Filter markets by age, volume, and spread.  Pure function — no I/O."""
    now = datetime.now(timezone.utc)
    results: list[dict] = []

    for market in markets:
        # --- age filter ---
        dt = _parse_date(market)
        if dt is None:
            continue
        age_hours = (now - dt).total_seconds() / 3600
        if age_hours > max_age_hours:
            continue

        # --- volume filter ---
        volume = _get_volume(market)
        if volume >= max_volume:
            continue

        # --- spread filter ---
        token_ids = _extract_token_ids(market)
        if not token_ids:
            continue
        # A market passes the spread filter if *any* of its tokens has wide spread
        max_token_spread = max((spreads.get(tid, 0.0) for tid in token_ids), default=0.0)
        if max_token_spread < min_spread:
            continue

        results.append(market)

    return results


# ---------------------------------------------------------------------------
# Orchestrator — fetch + filter
# ---------------------------------------------------------------------------


async def _fetch_spread(session: aiohttp.ClientSession, clob_url: str, token_id: str) -> float:
    """Fetch spread for a single token. Returns 0.0 on error."""
    try:
        async with session.get(f"{clob_url}/spread", params={"token_id": token_id}) as resp:
            if resp.status != 200:
                return 0.0
            data = await resp.json()
            return float(data.get("spread", 0.0))
    except Exception:
        log.exception("Failed to fetch spread for token %s", token_id)
        return 0.0


async def scan_opportunities(
    session: aiohttp.ClientSession,
    gamma_url: str,
    clob_url: str,
    max_volume: float,
    min_spread: float,
) -> list[dict]:
    """Fetch recent markets, filter by age/volume, fetch spreads, filter by spread."""

    # 1. Fetch recent markets from Gamma
    try:
        async with session.get(
            f"{gamma_url}/markets",
            params={
                "limit": 20,
                "active": "true",
                "closed": "false",
                "order": "startDate",
                "ascending": "false",
            },
        ) as resp:
            if resp.status != 200:
                log.warning("Gamma API /markets returned %s", resp.status)
                return []
            markets = await resp.json()
    except Exception:
        log.exception("Failed to fetch markets from Gamma API")
        return []

    # 2. Pre-filter by age and volume (cheap, no extra API calls)
    now = datetime.now(timezone.utc)
    candidates: list[dict] = []
    for m in markets:
        dt = _parse_date(m)
        if dt is None:
            continue
        age_hours = (now - dt).total_seconds() / 3600
        if age_hours > 48:
            continue
        vol = _get_volume(m)
        if vol >= max_volume:
            continue
        candidates.append(m)

    # 3. Fetch spreads for remaining candidates (sequential to avoid rate limits)
    spreads: dict[str, float] = {}
    for m in candidates:
        token_ids = _extract_token_ids(m)
        for tid in token_ids:
            if tid not in spreads:
                spreads[tid] = await _fetch_spread(session, clob_url, tid)

    # 4. Final filter including spread
    return filter_opportunities(
        markets=candidates,
        spreads=spreads,
        max_volume=max_volume,
        min_spread=min_spread,
        max_age_hours=48,
    )


# ---------------------------------------------------------------------------
# Discord Cog
# ---------------------------------------------------------------------------


def _format_opportunities_embeds(opportunities: list[dict]) -> list[discord.Embed]:
    """Format opportunities as embeds. Returns a list with one embed."""
    if not opportunities:
        embed = discord.Embed(
            title="Opportunity Scan",
            description="No opportunities found this scan.",
            colour=discord.Colour.greyple(),
        )
        return [embed]

    return format_market_list(
        opportunities,
        page=0,
        per_page=min(len(opportunities), 10),
        sort="volume",
    )


class OpportunitiesCog(commands.Cog, name="Opportunities"):
    """Hourly scan for low-liquidity new markets."""

    def __init__(self, bot: PolymarketBot) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        from polymarket_bot.config import settings

        self.gamma_url = settings.gamma_api_url
        self.clob_url = settings.clob_api_url
        self.channel_id = settings.opportunity_channel_id
        self.max_volume = settings.opportunity_max_volume
        self.min_spread = settings.opportunity_min_spread
        self.session = aiohttp.ClientSession()
        self.scan_loop.start()

    async def cog_unload(self) -> None:
        self.scan_loop.cancel()
        if self.session:
            await self.session.close()

    @tasks.loop(hours=1)
    async def scan_loop(self) -> None:
        if not self.session or not self.channel_id:
            return

        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            log.warning("Opportunity channel %s not found", self.channel_id)
            return

        opportunities = await scan_opportunities(
            session=self.session,
            gamma_url=self.gamma_url,
            clob_url=self.clob_url,
            max_volume=self.max_volume,
            min_spread=self.min_spread,
        )

        if opportunities:
            embeds = _format_opportunities_embeds(opportunities)
            embeds[0].title = f"🔍 Opportunities ({len(opportunities)} found)"
            embeds[0].colour = discord.Colour.purple()
            await channel.send(embeds=embeds)

    @scan_loop.before_loop
    async def before_scan_loop(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="opportunities",
        description="Manually scan for low-liquidity market opportunities",
    )
    async def opportunities_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        if not self.session:
            await interaction.followup.send("Session not ready.")
            return

        opportunities = await scan_opportunities(
            session=self.session,
            gamma_url=self.gamma_url,
            clob_url=self.clob_url,
            max_volume=self.max_volume,
            min_spread=self.min_spread,
        )

        per_page = 5
        title = f"🔍 Opportunities ({len(opportunities)} found)"
        colour = discord.Colour.purple()

        embeds = format_market_list(opportunities, page=0, per_page=per_page)
        embeds[0].title = title
        embeds[0].colour = colour

        num_pages = total_pages(len(opportunities), per_page)
        kwargs: dict = {"embeds": embeds}
        if num_pages > 1:
            kwargs["view"] = MarketPaginationView(opportunities, per_page=per_page, title=title, colour=colour)
        await interaction.followup.send(**kwargs)


async def setup(bot: PolymarketBot) -> None:
    await bot.add_cog(OpportunitiesCog(bot))
