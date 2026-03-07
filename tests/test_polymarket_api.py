"""Contract tests for the Polymarket Gamma API /events endpoint.

These tests make real HTTP calls to verify the API returns data in the
shape that fetch_trending_events() depends on.
"""

from datetime import datetime, timedelta, timezone

import aiohttp
import pytest

GAMMA_API_URL = "https://gamma-api.polymarket.com"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as s:
        yield s


class TestListEvents:
    """GET /events — list active events."""

    async def test_returns_list(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/events",
            params={"limit": 5, "active": "true", "closed": "false"},
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert isinstance(data, list)

    async def test_returns_requested_limit(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/events",
            params={"limit": 3, "active": "true", "closed": "false"},
        ) as resp:
            data = await resp.json()
            assert len(data) <= 3

    async def test_event_has_expected_fields(self, session: aiohttp.ClientSession):
        """Verify the fields that fetch_trending_events and formatting depend on."""
        async with session.get(
            f"{GAMMA_API_URL}/events",
            params={"limit": 1, "active": "true", "closed": "false"},
        ) as resp:
            data = await resp.json()
            assert len(data) > 0
            event = data[0]
            assert "title" in event
            assert "slug" in event
            assert "volume" in event
            assert "tags" in event
            assert "markets" in event
            assert "startDate" in event or "createdAt" in event

    async def test_tags_are_list_of_dicts_with_label(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/events",
            params={"limit": 5, "active": "true", "closed": "false"},
        ) as resp:
            data = await resp.json()
            for event in data:
                tags = event.get("tags") or []
                assert isinstance(tags, list)
                for tag in tags:
                    assert isinstance(tag, dict)
                    assert "label" in tag

    async def test_markets_is_nested_list(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/events",
            params={"limit": 3, "active": "true", "closed": "false"},
        ) as resp:
            data = await resp.json()
            for event in data:
                markets = event.get("markets") or []
                assert isinstance(markets, list)


class TestEventsFiltering:
    """GET /events — filtering and ordering parameters."""

    async def test_start_date_min_filter(self, session: aiohttp.ClientSession):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        async with session.get(
            f"{GAMMA_API_URL}/events",
            params={
                "limit": 5,
                "active": "true",
                "closed": "false",
                "start_date_min": cutoff_iso,
            },
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert isinstance(data, list)

    async def test_volume_ordering(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/events",
            params={
                "limit": 5,
                "active": "true",
                "closed": "false",
                "order": "volume",
                "ascending": "false",
            },
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            if len(data) >= 2:
                first_vol = float(data[0].get("volume") or 0)
                second_vol = float(data[1].get("volume") or 0)
                assert first_vol >= second_vol

    async def test_pagination_with_offset(self, session: aiohttp.ClientSession):
        params = {"limit": 2, "active": "true", "closed": "false", "order": "volume", "ascending": "false"}
        async with session.get(f"{GAMMA_API_URL}/events", params=params) as resp:
            page0 = await resp.json()

        params["offset"] = 2
        async with session.get(f"{GAMMA_API_URL}/events", params=params) as resp:
            page1 = await resp.json()

        if page0 and page1:
            page0_slugs = {e["slug"] for e in page0}
            page1_slugs = {e["slug"] for e in page1}
            assert page0_slugs.isdisjoint(page1_slugs), "Pages should not overlap"
