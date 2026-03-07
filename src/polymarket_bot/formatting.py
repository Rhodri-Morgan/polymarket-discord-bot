"""Shared market embed formatting — used by both slash commands and scheduled posts."""

from __future__ import annotations

import json
import math

import discord

from polymarket_bot import market_url


def _parse_json_field(value) -> list:
    """Parse a JSON-encoded string or return the value if already a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return []


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


def _outcome_emoji(name: str, pct: float) -> str:
    """Pick an emoji for an outcome based on its name and probability."""
    low = name.lower()
    if low == "yes":
        return "🟢" if pct >= 50 else "🔴"
    if low == "no":
        return "🔴" if pct >= 50 else "🟢"
    # Multi-outcome: use bar chart style
    if pct >= 40:
        return "🥇"
    if pct >= 20:
        return "🥈"
    return "🥉"


def parse_outcomes(market: dict) -> list[tuple[str, float]]:
    """Parse outcomes and their prices from a market dict.

    Returns a list of (outcome_name, percentage) tuples.
    """
    outcomes = _parse_json_field(market.get("outcomes"))
    prices = _parse_json_field(market.get("outcomePrices"))

    if not outcomes or not prices or len(outcomes) != len(prices):
        return []

    result = []
    for name, price in zip(outcomes, prices):
        try:
            pct = float(price) * 100
        except (TypeError, ValueError):
            pct = 0.0
        result.append((name, round(pct, 1)))
    return result


def total_pages(num_items: int, per_page: int) -> int:
    """Calculate total number of pages."""
    if num_items == 0:
        return 0
    return math.ceil(num_items / per_page)


def format_market_embed(market: dict) -> discord.Embed:
    """Format a single market as an embed field-style card.

    Returns an Embed with the question as the title, a URL link,
    and fields for volume and outcome prices.
    """
    question = market.get("question", "Unknown Market")
    link = market_url(market)
    volume = market.get("volume", market.get("volumeNum", 0))

    embed = discord.Embed(
        title=f"📊 {question}",
        url=link or None,
        colour=discord.Colour.blue(),
    )

    # Outcomes line
    outcomes = parse_outcomes(market)
    if outcomes:
        outcome_parts = []
        for name, pct in outcomes:
            emoji = _outcome_emoji(name, pct)
            outcome_parts.append(f"{emoji} **{name}**: {pct:.0f}%")
        embed.add_field(name="📈 Prices", value=" / ".join(outcome_parts), inline=True)

    embed.add_field(name="💰 Volume", value=_format_volume(volume), inline=True)

    if link:
        embed.add_field(name="🔗 Link", value=f"[View on Polymarket]({link})", inline=False)

    return embed


def format_market_list(
    markets: list[dict],
    page: int = 0,
    per_page: int = 5,
    sort: str = "volume",
) -> list[discord.Embed]:
    """Format a list of markets into paginated embeds.

    Args:
        markets: List of market dicts from the Gamma API.
        page: Zero-indexed page number.
        per_page: Markets per page.
        sort: Sort key — "volume" (default) sorts by volume descending.

    Returns:
        A list containing a single Embed with fields for each market on the page.
    """
    if not markets:
        embed = discord.Embed(
            title="Markets",
            description="No markets found.",
            colour=discord.Colour.greyple(),
        )
        return [embed]

    # Sort
    if sort == "volume":
        markets = sorted(markets, key=lambda m: _safe_float(m.get("volume", 0)), reverse=True)

    # Paginate
    total = len(markets)
    start = page * per_page
    end = min(start + per_page, total)
    page_markets = markets[start:end]

    num_pages = total_pages(total, per_page)
    embed = discord.Embed(
        title="📊 Active Markets",
        colour=discord.Colour.blue(),
    )

    for i, market in enumerate(page_markets, start + 1):
        question = market.get("question", "Unknown")
        link = market_url(market)
        volume = market.get("volume", market.get("volumeNum", 0))

        # Build compact field value
        lines = []

        outcomes = parse_outcomes(market)
        if outcomes:
            outcome_parts = []
            for name, pct in outcomes:
                emoji = _outcome_emoji(name, pct)
                outcome_parts.append(f"{emoji} **{name}**: {pct:.0f}%")
            lines.append(" / ".join(outcome_parts))

        vol_line = f"💰 {_format_volume(volume)}"
        if link:
            vol_line += f" · [🔗 View]({link})"
        lines.append(vol_line)

        embed.add_field(
            name=f"{i}. {question}",
            value="\n".join(lines),
            inline=False,
        )

    embed.set_footer(text=f"📄 Showing {start + 1}–{end} of {total} markets · Page {page + 1}/{num_pages}")

    return [embed]


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
