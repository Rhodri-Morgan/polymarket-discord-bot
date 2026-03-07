"""Polymarket Discord Bot."""


def market_url(market: dict) -> str:
    """Build a Polymarket URL for a market dict.

    Uses the event slug (not market slug) since Polymarket routes via
    ``/event/{event_slug}/{market_slug}``.
    """
    market_slug = market.get("slug", "")
    events = market.get("events") or []
    event_slug = events[0].get("slug", "") if events else ""

    if event_slug and market_slug and event_slug != market_slug:
        return f"https://polymarket.com/event/{event_slug}/{market_slug}"
    if event_slug:
        return f"https://polymarket.com/event/{event_slug}"
    if market_slug:
        return f"https://polymarket.com/event/{market_slug}"
    return ""
