"""Volume Movers cog — hourly snapshots + daily volume change report."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from polymarket_bot import store

if TYPE_CHECKING:
    from polymarket_bot.bot import PolymarketBot

log = logging.getLogger(__name__)

SNAPSHOT_FILE = "volume_snapshots"
MAX_SNAPSHOT_AGE_HOURS = 25
TOP_N = 10


# ---------------------------------------------------------------------------
# Standalone functions (testable without Discord)
# ---------------------------------------------------------------------------


async def _fetch_active_markets(session: Any, gamma_url: str) -> list[dict]:
    """Fetch all active markets from the Gamma API, paginating as needed."""
    all_markets: list[dict] = []
    limit = 100
    offset = 0

    while True:
        url = f"{gamma_url}/markets"
        params = {
            "limit": limit,
            "offset": offset,
            "active": "true",
            "closed": "false",
        }
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                log.warning("Gamma API /markets returned %s", resp.status)
                break
            batch = await resp.json()
            if not batch:
                break
            all_markets.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

    return all_markets


async def take_snapshot(session: Any, gamma_url: str) -> None:
    """Fetch all active markets, save a volume snapshot, prune old entries."""
    markets = await _fetch_active_markets(session, gamma_url)
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    snapshot: dict[str, dict] = {}
    for market in markets:
        market_id = market.get("id")
        if not market_id:
            continue
        question = market.get("question", "")
        volume_raw = market.get("volume", 0)
        try:
            volume = float(volume_raw)
        except (TypeError, ValueError):
            volume = 0.0
        snapshot[market_id] = {"question": question, "volume": volume}

    data = await store.load(SNAPSHOT_FILE)
    snapshots = data.get("snapshots", {})
    snapshots[now_ts] = snapshot

    # Prune entries older than 25 hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_SNAPSHOT_AGE_HOURS)
    to_remove = []
    for ts_str in snapshots:
        ts_dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if ts_dt < cutoff:
            to_remove.append(ts_str)
    for ts_str in to_remove:
        del snapshots[ts_str]

    await store.save(SNAPSHOT_FILE, {"snapshots": snapshots})
    log.info("Volume snapshot saved with %d markets (%d snapshots total)", len(snapshot), len(snapshots))


async def generate_report() -> dict | None:
    """Load snapshots, compare latest vs closest-to-24h-ago, return report or None.

    Returns ``{"absolute": [...], "percentage": [...]}`` where each list contains
    dicts with market_id, question, old_volume, new_volume, abs_change, pct_change.
    Returns None if there aren't enough snapshots for a comparison.
    """
    data = await store.load(SNAPSHOT_FILE)
    snapshots = data.get("snapshots", {})

    if len(snapshots) < 2:
        return None

    # Parse timestamps and sort
    parsed: list[tuple[datetime, str]] = []
    for ts_str in snapshots:
        ts_dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        parsed.append((ts_dt, ts_str))
    parsed.sort(key=lambda x: x[0])

    latest_dt, latest_key = parsed[-1]
    target_dt = latest_dt - timedelta(hours=24)

    # Find the snapshot closest to 24h ago (excluding the latest itself)
    best_delta = None
    best_key = None
    for ts_dt, ts_key in parsed[:-1]:
        delta = abs((ts_dt - target_dt).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_key = ts_key

    if best_key is None:
        return None

    old_snap = snapshots[best_key]
    new_snap = snapshots[latest_key]

    # Compare: iterate over markets in the latest snapshot
    entries = []
    for market_id, new_data in new_snap.items():
        new_vol = new_data.get("volume", 0)
        old_data = old_snap.get(market_id)
        old_vol = old_data["volume"] if old_data else 0
        question = new_data.get("question", "")

        abs_change = new_vol - old_vol
        if old_vol > 0:
            pct_change = (abs_change / old_vol) * 100
        else:
            pct_change = float("inf") if new_vol > 0 else 0.0

        entries.append(
            {
                "market_id": market_id,
                "question": question,
                "old_volume": old_vol,
                "new_volume": new_vol,
                "abs_change": abs_change,
                "pct_change": pct_change,
            }
        )

    # Rank by absolute increase (descending), top N
    by_absolute = sorted(entries, key=lambda e: e["abs_change"], reverse=True)[:TOP_N]

    # Rank by percentage increase (descending), top N
    by_percentage = sorted(entries, key=lambda e: e["pct_change"], reverse=True)[:TOP_N]

    return {"absolute": by_absolute, "percentage": by_percentage}


def format_report(report: dict) -> str:
    """Format a report dict into plain text for Discord."""
    lines = ["**Volume Movers — Last 24 Hours**\n"]

    lines.append("**Top 10 by Absolute Volume Increase:**")
    for i, entry in enumerate(report["absolute"], 1):
        abs_change = entry["abs_change"]
        new_vol = entry["new_volume"]
        question = entry["question"]
        lines.append(f"{i}. {question} — +${abs_change:,.0f} (now ${new_vol:,.0f})")

    lines.append("")
    lines.append("**Top 10 by Percentage Volume Increase:**")
    for i, entry in enumerate(report["percentage"], 1):
        pct = entry["pct_change"]
        new_vol = entry["new_volume"]
        question = entry["question"]
        if pct == float("inf"):
            pct_str = "new"
        else:
            pct_str = f"+{pct:.1f}%"
        lines.append(f"{i}. {question} — {pct_str} (now ${new_vol:,.0f})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Discord Cog
# ---------------------------------------------------------------------------


class VolumeMoversCog(commands.Cog, name="Volume Movers"):
    """Hourly volume snapshots with a daily report of biggest movers."""

    def __init__(self, bot: PolymarketBot) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        from polymarket_bot.config import settings

        self.gamma_url = settings.gamma_api_url
        self.report_channel_id = settings.volume_report_channel_id
        self.report_hour = settings.volume_report_hour
        self.session = aiohttp.ClientSession()
        self.snapshot_loop.start()

    async def cog_unload(self) -> None:
        self.snapshot_loop.cancel()
        if self.session:
            await self.session.close()

    @tasks.loop(hours=1)
    async def snapshot_loop(self) -> None:
        """Take an hourly snapshot. At report hour, also post the daily report."""
        if not self.session:
            return

        await take_snapshot(self.session, self.gamma_url)

        now_utc = datetime.now(timezone.utc)
        if now_utc.hour == self.report_hour:
            await self._post_report()

    @snapshot_loop.before_loop
    async def before_snapshot_loop(self) -> None:
        await self.bot.wait_until_ready()

    async def _post_report(self) -> None:
        """Generate and post the volume report to the configured channel."""
        if not self.report_channel_id:
            log.warning("No VOLUME_REPORT_CHANNEL_ID configured, skipping report")
            return

        report = await generate_report()
        if report is None:
            log.info("Not enough snapshot data for a volume report yet")
            return

        channel = self.bot.get_channel(self.report_channel_id)
        if channel is None:
            log.warning("Could not find channel %s", self.report_channel_id)
            return

        text = format_report(report)
        # Discord has a 2000 char limit; truncate if needed
        if len(text) > 2000:
            text = text[:1997] + "..."
        await channel.send(text)
        log.info("Volume movers report posted to channel %s", self.report_channel_id)

    @app_commands.command(
        name="volume-movers",
        description="Show the biggest volume movers in the last 24 hours",
    )
    async def volume_movers_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        report = await generate_report()
        if report is None:
            await interaction.followup.send("Not enough data yet — need at least two snapshots ~24h apart.")
            return

        text = format_report(report)
        if len(text) > 2000:
            text = text[:1997] + "..."
        await interaction.followup.send(text)


async def setup(bot: PolymarketBot) -> None:
    await bot.add_cog(VolumeMoversCog(bot))
