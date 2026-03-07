"""Tests for market_url helper."""

from polymarket_bot import market_url


def test_single_market_event():
    """When market slug matches event slug, use the simple /event/{slug} URL."""
    market = {
        "slug": "bitboy-convicted",
        "events": [{"slug": "bitboy-convicted"}],
    }
    assert market_url(market) == "https://polymarket.com/event/bitboy-convicted"


def test_multi_market_event():
    """When market slug differs from event slug, include both in the URL."""
    market = {
        "slug": "russia-ukraine-ceasefire-before-gta-vi-554",
        "events": [{"slug": "what-will-happen-before-gta-vi"}],
    }
    assert market_url(market) == ("https://polymarket.com/event/what-will-happen-before-gta-vi" "/russia-ukraine-ceasefire-before-gta-vi-554")


def test_no_events_falls_back_to_market_slug():
    """When events list is missing, fall back to market slug."""
    market = {"slug": "some-market"}
    assert market_url(market) == "https://polymarket.com/event/some-market"


def test_empty_events_falls_back_to_market_slug():
    """When events list is empty, fall back to market slug."""
    market = {"slug": "some-market", "events": []}
    assert market_url(market) == "https://polymarket.com/event/some-market"


def test_no_slug_returns_empty_string():
    """When no slug is available at all, return empty string."""
    assert market_url({}) == ""


def test_real_api_urls():
    """Verify URLs against real Gamma API data."""
    import requests

    resp = requests.get(
        "https://gamma-api.polymarket.com/markets",
        params={"limit": 5, "active": "true", "closed": "false"},
    )
    resp.raise_for_status()
    markets = resp.json()

    for m in markets:
        url = market_url(m)
        assert url.startswith("https://polymarket.com/event/"), f"Bad URL for {m.get('slug')}: {url}"
        events = m.get("events", [])
        if events:
            event_slug = events[0].get("slug", "")
            assert event_slug in url, f"Event slug '{event_slug}' not in URL: {url}"
