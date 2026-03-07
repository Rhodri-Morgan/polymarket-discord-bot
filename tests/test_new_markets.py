"""Tests for the new_markets cog — check_new_markets logic."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from polymarket_bot import store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _use_tmp_data_dir(tmp_path, monkeypatch):
    """Point store.DATA_DIR at a temporary directory for every test."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


def _make_market(id_: str, question: str = "Will X?", slug: str = "will-x") -> dict:
    """Return a market dict matching the real Gamma API response shape.

    Key details from the real API:
    - id is a string (e.g. "531202")
    - volume is a string (e.g. "62981.410581999815")
    - outcomes is a JSON-encoded string
    - clobTokenIds is a JSON-encoded string
    """
    return {
        "id": id_,
        "question": question,
        "slug": slug,
        "active": True,
        "closed": False,
        "volume": "1000",
        "volumeNum": 1000,
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["fake_token_1", "fake_token_2"]',
        "startDate": "2026-03-07T12:00:00Z",
        "createdAt": "2026-03-07T12:00:00Z",
    }


def _fake_session(markets: list[dict]) -> MagicMock:
    """Return a mock aiohttp session whose GET always returns *markets*.

    ``session.get(...)`` must be a regular call (not a coroutine) that
    returns an async context manager, matching aiohttp's real behaviour.
    """
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(return_value=markets)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_cold_start_populates_seen_markets(tmp_path):
    """When seen_markets.json is missing, the first run saves all IDs and
    returns an empty list (nothing to alert)."""
    from polymarket_bot.cogs.new_markets import check_new_markets

    markets = [_make_market("m1"), _make_market("m2"), _make_market("m3")]
    session = _fake_session(markets)

    new = await check_new_markets(session, "https://fake.api")
    assert new == []

    # State file should now contain all three IDs
    state = await store.load("seen_markets")
    assert set(state["seen_ids"]) == {"m1", "m2", "m3"}


async def test_cold_start_posts_nothing(tmp_path):
    """On cold start the function returns an empty list — the cog should
    therefore send nothing to the channel."""
    from polymarket_bot.cogs.new_markets import check_new_markets

    markets = [_make_market("m1"), _make_market("m2")]
    session = _fake_session(markets)

    new = await check_new_markets(session, "https://fake.api")
    assert new == []


async def test_second_run_detects_new_market(tmp_path):
    """Pre-populate seen_markets.json, then run with an extra market.
    Only the new market should be returned."""
    from polymarket_bot.cogs.new_markets import check_new_markets

    # Seed state as if a previous run happened
    await store.save(
        "seen_markets",
        {
            "seen_ids": ["m1", "m2"],
            "last_check": "2026-03-07T12:00:00Z",
        },
    )

    markets = [_make_market("m1"), _make_market("m2"), _make_market("m3", "Will Y?", "will-y")]
    session = _fake_session(markets)

    new = await check_new_markets(session, "https://fake.api")
    assert len(new) == 1
    assert new[0]["id"] == "m3"


async def test_second_run_no_new_markets(tmp_path):
    """When the API returns exactly the same IDs, nothing new is detected."""
    from polymarket_bot.cogs.new_markets import check_new_markets

    await store.save(
        "seen_markets",
        {
            "seen_ids": ["m1", "m2"],
            "last_check": "2026-03-07T12:00:00Z",
        },
    )

    markets = [_make_market("m1"), _make_market("m2")]
    session = _fake_session(markets)

    new = await check_new_markets(session, "https://fake.api")
    assert new == []


async def test_pruning_removes_inactive_ids(tmp_path):
    """IDs for markets no longer in the active response get removed from
    the state file."""
    from polymarket_bot.cogs.new_markets import check_new_markets

    # m3 exists in state but will NOT be in the API response
    await store.save(
        "seen_markets",
        {
            "seen_ids": ["m1", "m2", "m3"],
            "last_check": "2026-03-07T12:00:00Z",
        },
    )

    markets = [_make_market("m1"), _make_market("m2")]
    session = _fake_session(markets)

    await check_new_markets(session, "https://fake.api")

    state = await store.load("seen_markets")
    assert "m3" not in state["seen_ids"]
    assert set(state["seen_ids"]) == {"m1", "m2"}


async def test_state_persists_across_calls(tmp_path):
    """Run the check twice. The second call should see state from the first."""
    from polymarket_bot.cogs.new_markets import check_new_markets

    # First run — cold start with m1, m2
    markets_run1 = [_make_market("m1"), _make_market("m2")]
    session1 = _fake_session(markets_run1)
    new1 = await check_new_markets(session1, "https://fake.api")
    assert new1 == []

    # Second run — m3 is new
    markets_run2 = [_make_market("m1"), _make_market("m2"), _make_market("m3", "Will Z?", "will-z")]
    session2 = _fake_session(markets_run2)
    new2 = await check_new_markets(session2, "https://fake.api")
    assert len(new2) == 1
    assert new2[0]["id"] == "m3"

    # State should contain all three
    state = await store.load("seen_markets")
    assert set(state["seen_ids"]) == {"m1", "m2", "m3"}
