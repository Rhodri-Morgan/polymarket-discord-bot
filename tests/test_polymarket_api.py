"""Tests for Polymarket Gamma API and CLOB API integration.

These tests make real HTTP calls to the public Polymarket APIs
to verify endpoints return data in the expected shape.
"""

import json

import aiohttp
import pytest

GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
async def token_id(session: aiohttp.ClientSession):
    """Fetch a real token_id from the Gamma API for use in CLOB tests."""
    async with session.get(
        f"{GAMMA_API_URL}/markets",
        params={"limit": 10, "active": "true", "closed": "false"},
    ) as resp:
        assert resp.status == 200
        markets = await resp.json()

    for market in markets:
        # Try clobTokenIds first (JSON-encoded list of token IDs)
        clob_token_ids = market.get("clobTokenIds")
        if clob_token_ids:
            if isinstance(clob_token_ids, str):
                try:
                    ids = json.loads(clob_token_ids)
                except (json.JSONDecodeError, TypeError):
                    ids = []
            else:
                ids = clob_token_ids
            if ids and len(ids) > 0:
                return ids[0]

        # Fall back to tokens list
        tokens = market.get("tokens")
        if tokens:
            if isinstance(tokens, str):
                try:
                    tokens = json.loads(tokens)
                except (json.JSONDecodeError, TypeError):
                    tokens = []
            if tokens and len(tokens) > 0:
                token = tokens[0]
                tid = token.get("token_id") or token.get("tokenId")
                if tid:
                    return tid

    pytest.fail("Could not find a valid token_id from any active market")


class TestListMarkets:
    """GET /markets — list active markets."""

    async def test_returns_list(self, session: aiohttp.ClientSession):
        async with session.get(f"{GAMMA_API_URL}/markets", params={"limit": 5, "active": "true", "closed": "false"}) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert isinstance(data, list)

    async def test_returns_requested_limit(self, session: aiohttp.ClientSession):
        async with session.get(f"{GAMMA_API_URL}/markets", params={"limit": 3, "active": "true", "closed": "false"}) as resp:
            data = await resp.json()
            assert len(data) <= 3

    async def test_market_has_expected_fields(self, session: aiohttp.ClientSession):
        async with session.get(f"{GAMMA_API_URL}/markets", params={"limit": 1, "active": "true", "closed": "false"}) as resp:
            data = await resp.json()
            assert len(data) > 0
            market = data[0]
            assert "question" in market
            assert "slug" in market
            assert "volume" in market
            assert "outcomes" in market
            assert "active" in market

    async def test_returned_markets_are_active(self, session: aiohttp.ClientSession):
        async with session.get(f"{GAMMA_API_URL}/markets", params={"limit": 5, "active": "true", "closed": "false"}) as resp:
            data = await resp.json()
            for market in data:
                assert market["active"] is True
                assert market["closed"] is False


class TestListMarketsPagination:
    """GET /markets — pagination via the limit parameter."""

    async def test_limit_one_returns_exactly_one(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/markets",
            params={"limit": 1, "active": "true", "closed": "false"},
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert len(data) == 1

    async def test_limit_ten_returns_up_to_ten(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/markets",
            params={"limit": 10, "active": "true", "closed": "false"},
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert 1 <= len(data) <= 10

    async def test_different_limits_return_different_counts(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/markets",
            params={"limit": 1, "active": "true", "closed": "false"},
        ) as resp:
            data_1 = await resp.json()

        async with session.get(
            f"{GAMMA_API_URL}/markets",
            params={"limit": 10, "active": "true", "closed": "false"},
        ) as resp:
            data_10 = await resp.json()

        assert len(data_1) != len(data_10)


class TestListMarketsOrdering:
    """GET /markets — ordering by volume."""

    async def test_descending_volume_order(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/markets",
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
            assert len(data) >= 2, "Need at least 2 markets to verify ordering"
            first_volume = float(data[0]["volume"])
            second_volume = float(data[1]["volume"])
            assert first_volume >= second_volume


class TestClobPrice:
    """GET /price — token price from the CLOB API."""

    async def test_returns_price(self, session: aiohttp.ClientSession, token_id: str):
        async with session.get(
            f"{CLOB_API_URL}/price",
            params={"token_id": token_id, "side": "buy"},
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "price" in data

    async def test_price_is_valid_float_between_0_and_1(self, session: aiohttp.ClientSession, token_id: str):
        async with session.get(
            f"{CLOB_API_URL}/price",
            params={"token_id": token_id, "side": "buy"},
        ) as resp:
            data = await resp.json()
            price = float(data["price"])
            assert 0 <= price <= 1


class TestClobMidpoint:
    """GET /midpoint — midpoint price from the CLOB API."""

    async def test_returns_mid(self, session: aiohttp.ClientSession, token_id: str):
        async with session.get(f"{CLOB_API_URL}/midpoint", params={"token_id": token_id}) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "mid" in data


class TestClobSpread:
    """GET /spread — spread from the CLOB API."""

    async def test_returns_spread(self, session: aiohttp.ClientSession, token_id: str):
        async with session.get(f"{CLOB_API_URL}/spread", params={"token_id": token_id}) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "spread" in data


class TestClobBook:
    """GET /book — order book from the CLOB API."""

    async def test_returns_bids_and_asks(self, session: aiohttp.ClientSession, token_id: str):
        async with session.get(f"{CLOB_API_URL}/book", params={"token_id": token_id}) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "bids" in data
            assert "asks" in data
            assert isinstance(data["bids"], list)
            assert isinstance(data["asks"], list)

    async def test_book_entries_have_price_and_size(self, session: aiohttp.ClientSession, token_id: str):
        async with session.get(f"{CLOB_API_URL}/book", params={"token_id": token_id}) as resp:
            data = await resp.json()
            # Check bids if any exist
            for entry in data["bids"]:
                assert "price" in entry
                assert "size" in entry
            # Check asks if any exist
            for entry in data["asks"]:
                assert "price" in entry
                assert "size" in entry
