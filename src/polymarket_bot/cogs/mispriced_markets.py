"""Mispriced Markets cog — detects arbitrage opportunities on negRisk events."""

from __future__ import annotations

import json
import logging
from datetime import datetime, time, timezone
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from polymarket_bot.formatting import _format_volume

if TYPE_CHECKING:
    from polymarket_bot.bot import PolymarketBot

log = logging.getLogger(__name__)

MIN_EVENT_LIQUIDITY = 10_000
MIN_MARKET_LIQUIDITY = 5_000
MAX_DEVIATION = 0.10
MAX_RESULTS = 100
EVENTS_PER_MESSAGE = 5


def _parse_yes_price(market: dict) -> float:
    """Extract the YES price from a market's outcomePrices field."""
    raw = market.get("outcomePrices")
    if not raw:
        return 0.0
    try:
        prices = json.loads(raw)
        if prices:
            return float(prices[0])
    except (json.JSONDecodeError, ValueError, TypeError, IndexError):
        pass
    return 0.0


def _active_markets(event: dict) -> list[dict]:
    """Return only active, non-closed markets from an event."""
    return [m for m in (event.get("markets") or []) if m.get("active") and not m.get("closed")]


def _event_price_sum(event: dict) -> float:
    """Sum YES prices across all active markets in an event."""
    return sum(_parse_yes_price(m) for m in _active_markets(event))


def _event_deviation(event: dict) -> float:
    """Absolute deviation of the YES price sum from 1.0."""
    return abs(_event_price_sum(event) - 1.0)


def _market_liquidity(market: dict) -> float:
    """Extract liquidity as a float from a market dict."""
    for field in ("liquidityNum", "liquidity"):
        raw = market.get(field)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return 0.0


def _is_tradeable(event: dict) -> bool:
    """Check if an event has enough liquidity to actually execute an arb."""
    if not event.get("negRisk"):
        return False

    active = _active_markets(event)
    if len(active) < 2:
        return False

    total_liq = sum(_market_liquidity(m) for m in active)
    if total_liq < MIN_EVENT_LIQUIDITY:
        return False

    for m in active:
        if _market_liquidity(m) < MIN_MARKET_LIQUIDITY:
            return False

    return True


def rank_mispriced_events(events: list[dict]) -> list[dict]:
    """Filter to tradeable events and sort by deviation descending.

    Caps deviation at MAX_DEVIATION — larger deviations are structural
    (e.g. many low-probability outcomes, missing "Other" bucket) rather
    than genuine arbitrage opportunities.
    """
    tradeable = [e for e in events if _is_tradeable(e) and 0 < _event_deviation(e) <= MAX_DEVIATION]
    tradeable.sort(key=_event_deviation, reverse=True)
    return tradeable[:MAX_RESULTS]


async def fetch_mispriced_events(
    session: aiohttp.ClientSession,
    gamma_url: str,
) -> list[dict]:
    """Fetch negRisk events, filter for tradeability, rank by mispricing."""
    all_events: list[dict] = []
    offset = 0
    page_size = 100
    while True:
        params = {
            "active": "true",
            "closed": "false",
            "neg_risk": "true",
            "order": "liquidity",
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

    return rank_mispriced_events(all_events)


def _format_mispriced_event(event: dict, rank: int) -> discord.Embed:
    """Format a single mispriced event as a rich embed."""
    title = event.get("title", "Unknown Event")
    slug = event.get("slug", "")
    url = f"https://polymarket.com/event/{slug}" if slug else ""

    price_sum = _event_price_sum(event)
    deviation = _event_deviation(event)
    direction = "UNDERPRICED" if price_sum < 1.0 else "OVERPRICED"

    active = _active_markets(event)
    total_liq = sum(_market_liquidity(m) for m in active)

    if price_sum < 1.0:
        colour = discord.Colour.green()
        action = f"Buy YES on all outcomes for ${price_sum:.4f}, guaranteed $1.00 payout"
    else:
        colour = discord.Colour.red()
        action = f"YES prices sum to ${price_sum:.4f} — outcomes overpriced by {deviation * 100:.1f}pp"

    embed = discord.Embed(
        title=f"#{rank} {title}",
        url=url or None,
        colour=colour,
    )
    embed.add_field(
        name="Deviation",
        value=f"{deviation * 100:.1f}pp ({direction})",
        inline=True,
    )
    embed.add_field(
        name="YES Price Sum",
        value=f"{price_sum:.4f}",
        inline=True,
    )
    embed.add_field(
        name="Total Liquidity",
        value=_format_volume(total_liq),
        inline=True,
    )

    # Show top markets by liquidity
    sorted_markets = sorted(active, key=_market_liquidity, reverse=True)
    lines = []
    for m in sorted_markets[:8]:
        name = m.get("groupItemTitle") or m.get("question", "?")[:40]
        yes_price = _parse_yes_price(m)
        liq = _market_liquidity(m)
        lines.append(f"`{yes_price:.2%}` {name} ({_format_volume(liq)})")

    if len(sorted_markets) > 8:
        lines.append(f"*...and {len(sorted_markets) - 8} more outcomes*")

    embed.add_field(
        name=f"Outcomes ({len(active)} active)",
        value="\n".join(lines) or "No data",
        inline=False,
    )
    embed.add_field(
        name="Strategy",
        value=action,
        inline=False,
    )

    return embed


async def _post_mispriced_thread(
    channel: discord.TextChannel,
    events: list[dict],
) -> None:
    """Post a summary message, create a thread, and post events inside it."""
    now_str = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")

    summary = await channel.send(
        embed=discord.Embed(
            title=f"\u2696\ufe0f Mispriced Markets (Top {len(events)})",
            description=(
                f"NegRisk events where outcome YES prices don't sum to 1.0.\n"
                f"Sorted by deviation (most mispriced first).\n"
                f"Min market liquidity: {_format_volume(MIN_MARKET_LIQUIDITY)} | "
                f"Min event liquidity: {_format_volume(MIN_EVENT_LIQUIDITY)}\n"
                f"**Generated**: {now_str}"
            ),
            colour=discord.Colour.blue(),
        )
    )

    thread = await summary.create_thread(
        name=f"Mispriced Markets \u2014 {datetime.now(timezone.utc).strftime('%b %d %H:%M')} UTC",
    )

    for batch_start in range(0, len(events), EVENTS_PER_MESSAGE):
        batch = events[batch_start : batch_start + EVENTS_PER_MESSAGE]
        embeds = [_format_mispriced_event(e, batch_start + i + 1) for i, e in enumerate(batch)]
        await thread.send(embeds=embeds)


class MispricedMarketsCog(commands.Cog, name="MispricedMarkets"):
    """Detects mispriced markets on Polymarket negRisk events."""

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

    @tasks.loop(time=[time(hour=8, tzinfo=timezone.utc)])
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

        events = await fetch_mispriced_events(self.session, self.gamma_url)
        if not events:
            return

        log.info("Posting %d mispriced events to alert channel.", len(events))
        await _post_mispriced_thread(channel, events)

    @app_commands.command(
        name="mispriced",
        description="Find mispriced Polymarket events (arbitrage opportunities)",
    )
    async def mispriced_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if not self.session:
            await interaction.followup.send("Session not ready.")
            return

        events = await fetch_mispriced_events(self.session, self.gamma_url)
        if not events:
            await interaction.followup.send("No mispriced events found with sufficient liquidity.")
            return

        await interaction.followup.send("Scanning for mispriced markets...")
        channel = interaction.channel
        await _post_mispriced_thread(channel, events)


async def setup(bot: PolymarketBot) -> None:
    await bot.add_cog(MispricedMarketsCog(bot))
