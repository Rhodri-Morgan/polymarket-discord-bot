"""Trending Events cog — surfaces hot new Polymarket events by volume velocity."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from polymarket_bot.formatting import format_trending_events

if TYPE_CHECKING:
    from polymarket_bot.bot import PolymarketBot

log = logging.getLogger(__name__)

# Tags to exclude from trending results
EXCLUDED_TAGS: set[str] = {
    "sports",
    "soccer",
    "epl",
    "la liga",
    "serie a",
    "ligue 1",
    "bundesliga",
    "nba",
    "nhl",
    "hockey",
    "basketball",
    "golf",
    "pga tour",
    "fifa world cup",
    "champions league",
    "stanley cup",
    "nba finals",
    "nba champion",
    "esports",
    "counter strike 2",
    "games",
    "crypto",
    "crypto prices",
    "bitcoin",
    "airdrops",
    "stablecoins",
    "pre-market",
    "fdv",
    "token launch",
    "weather",
    "recurring",
}

LOOKBACK_HOURS = 48
MAX_RESULTS = 100
EVENTS_PER_MESSAGE = 10


def _event_tag_labels(event: dict) -> list[str]:
    """Extract lowercase tag labels from an event."""
    return [t.get("label", "").lower() for t in (event.get("tags") or []) if isinstance(t, dict)]


def _has_excluded_tag(event: dict) -> bool:
    """Return True if the event has any excluded tag."""
    return bool(EXCLUDED_TAGS & set(_event_tag_labels(event)))


def _volume_velocity(event: dict) -> float:
    """Calculate volume per hour since event creation."""
    volume = 0.0
    try:
        volume = float(event.get("volume") or 0)
    except (TypeError, ValueError):
        pass

    now = datetime.now(timezone.utc)
    for field in ("startDate", "createdAt"):
        raw = event.get(field)
        if raw:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_hours = max((now - dt).total_seconds() / 3600, 0.1)
                return volume / age_hours
            except (ValueError, TypeError):
                continue
    return volume


async def fetch_trending_events(
    session: aiohttp.ClientSession,
    gamma_url: str,
) -> list[dict]:
    """Fetch recent events, filter, and rank by volume velocity.

    No state needed — uses the Gamma API's start_date_min parameter.
    Returns up to MAX_RESULTS events sorted by volume/hour.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_events: list[dict] = []
    offset = 0
    page_size = 100
    while True:
        params = {
            "active": "true",
            "closed": "false",
            "start_date_min": cutoff_iso,
            "order": "volume",
            "ascending": "false",
            "limit": page_size,
            "offset": offset,
        }
        try:
            async with session.get(f"{gamma_url}/events", params=params) as resp:
                if resp.status != 200:
                    log.warning("Gamma API /events returned %s", resp.status)
                    break
                page = await resp.json()
        except Exception:
            log.exception("Failed to fetch events from Gamma API")
            break

        if not page:
            break
        all_events.extend(page)
        if len(all_events) >= 500 or len(page) < page_size:
            break
        offset += page_size

    # Filter out excluded categories
    filtered = [e for e in all_events if not _has_excluded_tag(e)]

    # Rank by volume velocity
    filtered.sort(key=_volume_velocity, reverse=True)

    return filtered[:MAX_RESULTS]


async def _post_trending_thread(
    channel: discord.TextChannel,
    events: list[dict],
) -> None:
    """Post a summary message, create a thread, and post all events inside it."""
    now_str = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    excluded_list = "Sports, Crypto, Weather, Esports"

    summary = await channel.send(
        embed=discord.Embed(
            title=f"\U0001f525 Trending Events (Top {len(events)})",
            description=(
                f"Top events from the last {LOOKBACK_HOURS}h ranked by volume velocity.\n"
                f"**Excluded**: {excluded_list}\n"
                f"**Generated**: {now_str}"
            ),
            colour=discord.Colour.orange(),
        )
    )

    thread = await summary.create_thread(
        name=f"Trending Events \u2014 {datetime.now(timezone.utc).strftime('%b %d %H:%M')} UTC",
    )

    # Post events in batches
    for batch_start in range(0, len(events), EVENTS_PER_MESSAGE):
        batch = events[batch_start : batch_start + EVENTS_PER_MESSAGE]
        embeds = format_trending_events(
            events,
            page=batch_start // EVENTS_PER_MESSAGE,
            per_page=EVENTS_PER_MESSAGE,
        )
        await thread.send(embeds=embeds)


class TrendingCog(commands.Cog, name="Trending"):
    """Surfaces trending new Polymarket events."""

    def __init__(self, bot: PolymarketBot) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        from polymarket_bot.config import settings

        self.gamma_url = settings.gamma_api_url
        self.channel_id = settings.discord_channel_id
        self.session = aiohttp.ClientSession()
        self.check_loop.start()

    async def cog_unload(self) -> None:
        self.check_loop.cancel()
        if self.session:
            await self.session.close()

    @tasks.loop(hours=12)
    async def check_loop(self) -> None:
        await self._run_check()

    @check_loop.before_loop
    async def before_check_loop(self) -> None:
        await self.bot.wait_until_ready()

    async def _run_check(self) -> None:
        if not self.session or not self.channel_id:
            return

        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            log.warning("Channel %s not found.", self.channel_id)
            return

        events = await fetch_trending_events(self.session, self.gamma_url)
        if not events:
            return

        log.info("Posting %d trending events to alert channel.", len(events))
        await _post_trending_thread(channel, events)

    @app_commands.command(name="trending", description=f"Top trending new Polymarket events (last {LOOKBACK_HOURS}h)")
    async def trending_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if not self.session:
            await interaction.followup.send("Session not ready.")
            return

        events = await fetch_trending_events(self.session, self.gamma_url)
        if not events:
            await interaction.followup.send("No trending events found.")
            return

        # Post summary to the channel, then create thread on it
        await interaction.followup.send("Fetching trending events...")
        channel = interaction.channel
        await _post_trending_thread(channel, events)


async def setup(bot: PolymarketBot) -> None:
    await bot.add_cog(TrendingCog(bot))
