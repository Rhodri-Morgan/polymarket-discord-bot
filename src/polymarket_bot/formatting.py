"""Shared formatting — used by both slash commands and scheduled posts."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import discord


_CATEGORY_EMOJI: dict[str, str] = {
    "politics": "\U0001f3db\ufe0f",
    "sports": "\u26bd",
    "crypto": "\U0001f4b0",
    "finance": "\U0001f4b0",
    "pop culture": "\U0001f3ac",
    "science": "\U0001f52c",
    "technology": "\U0001f4bb",
    "ai": "\U0001f916",
    "weather": "\U0001f324\ufe0f",
    "world": "\U0001f30d",
    "geopolitics": "\U0001f30d",
    "business": "\U0001f3e2",
    "health": "\U0001f3e5",
    "entertainment": "\U0001f3ac",
    "gaming": "\U0001f3ae",
    "culture": "\U0001f3ad",
}


def _format_volume(volume) -> str:
    """Format a volume value as a human-readable dollar string."""
    try:
        v = float(volume)
    except (TypeError, ValueError):
        return "$?"
    if v >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:,.1f}K"
    return f"${v:,.0f}"


def total_pages(num_items: int, per_page: int) -> int:
    """Calculate total number of pages."""
    if num_items == 0:
        return 0
    return math.ceil(num_items / per_page)


def _event_category_emoji(event: dict) -> str:
    """Return a category emoji for an event based on its tags."""
    tags = event.get("tags") or []
    for tag in tags:
        if isinstance(tag, dict):
            emoji = _CATEGORY_EMOJI.get(tag.get("label", "").lower())
            if emoji:
                return emoji
    return "\U0001f4ca"


def _format_age(event: dict) -> str:
    """Return a human-readable age string like '3h' or '1d 6h'."""
    now = datetime.now(timezone.utc)
    for field in ("startDate", "createdAt"):
        raw = event.get(field)
        if raw:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                delta = now - dt
                hours = int(delta.total_seconds() / 3600)
                if hours < 1:
                    return "<1h"
                if hours < 24:
                    return f"{hours}h"
                days = hours // 24
                remaining_hours = hours % 24
                if remaining_hours:
                    return f"{days}d {remaining_hours}h"
                return f"{days}d"
            except (ValueError, TypeError):
                continue
    return "?"


def format_trending_events(
    events: list[dict],
    page: int = 0,
    per_page: int = 10,
) -> list[discord.Embed]:
    """Format trending events as an embed for use in a thread message.

    Each event is one field: linked title, volume, age, number of markets.
    """
    if not events:
        embed = discord.Embed(
            title="Trending Events",
            description="No trending events found.",
            colour=discord.Colour.greyple(),
        )
        return [embed]

    total = len(events)
    start = page * per_page
    end = min(start + per_page, total)
    page_events = events[start:end]
    num_pages = total_pages(total, per_page)

    embed = discord.Embed(colour=discord.Colour.orange())

    for event in page_events:
        event_title = event.get("title", "Unknown Event")
        slug = event.get("slug", "")
        cat_emoji = _event_category_emoji(event)
        url = f"https://polymarket.com/event/{slug}" if slug else ""
        volume = event.get("volume") or 0
        num_markets = len(event.get("markets") or [])
        age = _format_age(event)

        if url:
            title_line = f"[{cat_emoji} {event_title}]({url})"
        else:
            title_line = f"{cat_emoji} {event_title}"

        value = f"{title_line}\n**Volume**: {_format_volume(volume)} \u00b7 **Age**: {age} \u00b7 **Markets**: {num_markets}"

        embed.add_field(
            name="\u200b",
            value=value,
            inline=False,
        )

    embed.set_footer(text=f"Showing {start + 1}\u2013{end} of {total} \u00b7 Page {page + 1}/{num_pages}")

    return [embed]
