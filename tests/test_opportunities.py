"""Tests for the Opportunity Finder — filtering logic (unit) and API integration.

Unit tests use mock data to verify filtering by volume, age, and spread.
Integration tests make real HTTP calls to public Polymarket APIs.
"""

import json
from datetime import datetime, timedelta, timezone

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


# ---------------------------------------------------------------------------
# Helpers — build mock market data
# ---------------------------------------------------------------------------


def _make_market(
    *,
    condition_id: str = "abc123",
    question: str = "Will it rain?",
    volume: float = 5000,
    created_at: str | None = None,
    clob_token_ids: list[str] | None = None,
) -> dict:
    """Build a mock market dict matching the real Gamma API response shape.

    Key details from the real API:
    - volume is a string (e.g. "62981.410581999815")
    - clobTokenIds is a JSON-encoded string (e.g. '["token_id_1", "token_id_2"]')
    - outcomes is a JSON-encoded string (e.g. '["Yes", "No"]')
    - startDate is ISO format with Z suffix (e.g. "2025-03-26T16:49:31.084Z")
    """
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    if clob_token_ids is None:
        clob_token_ids = ["token_1"]
    return {
        "id": condition_id,
        "conditionId": condition_id,
        "question": question,
        "volume": str(volume),
        "volumeNum": volume,
        "startDate": created_at,
        "createdAt": created_at,
        "clobTokenIds": json.dumps(clob_token_ids),
        "outcomes": json.dumps(["Yes", "No"]),
        "active": True,
        "closed": False,
        "slug": "will-it-rain",
        "liquidity": "1000",
        "liquidityNum": 1000,
    }


# ---------------------------------------------------------------------------
# Unit tests — filtering logic
# ---------------------------------------------------------------------------


class TestFilterByMaxVolume:
    """Markets with volume above max_volume should be excluded."""

    def test_filters_by_max_volume(self):
        from polymarket_bot.cogs.opportunities import filter_opportunities

        now = datetime.now(timezone.utc).isoformat()
        markets = [
            _make_market(condition_id="low", volume=5000, created_at=now),
            _make_market(condition_id="high", volume=50000, created_at=now),
        ]
        spreads = {"token_1": 0.10}

        result = filter_opportunities(
            markets=markets,
            spreads=spreads,
            max_volume=10000,
            min_spread=0.05,
            max_age_hours=48,
        )

        ids = [m["conditionId"] for m in result]
        assert "low" in ids
        assert "high" not in ids


class TestFilterByAge:
    """Markets older than max_age_hours should be excluded."""

    def test_filters_by_age(self):
        from polymarket_bot.cogs.opportunities import filter_opportunities

        recent = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()

        markets = [
            _make_market(condition_id="recent", created_at=recent),
            _make_market(condition_id="old", created_at=old),
        ]
        spreads = {"token_1": 0.10}

        result = filter_opportunities(
            markets=markets,
            spreads=spreads,
            max_volume=10000,
            min_spread=0.05,
            max_age_hours=48,
        )

        ids = [m["conditionId"] for m in result]
        assert "recent" in ids
        assert "old" not in ids


class TestFilterBySpread:
    """Markets with spread below min_spread should be excluded."""

    def test_filters_by_spread(self):
        from polymarket_bot.cogs.opportunities import filter_opportunities

        now = datetime.now(timezone.utc).isoformat()
        markets = [
            _make_market(
                condition_id="wide",
                created_at=now,
                clob_token_ids=["token_wide"],
            ),
            _make_market(
                condition_id="tight",
                created_at=now,
                clob_token_ids=["token_tight"],
            ),
        ]
        spreads = {"token_wide": 0.10, "token_tight": 0.02}

        result = filter_opportunities(
            markets=markets,
            spreads=spreads,
            max_volume=10000,
            min_spread=0.05,
            max_age_hours=48,
        )

        ids = [m["conditionId"] for m in result]
        assert "wide" in ids
        assert "tight" not in ids


class TestAllFiltersCombined:
    """A market must pass ALL criteria to be included."""

    def test_all_filters_combined(self):
        from polymarket_bot.cogs.opportunities import filter_opportunities

        now = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()

        markets = [
            # Passes all
            _make_market(
                condition_id="good",
                volume=5000,
                created_at=now,
                clob_token_ids=["tok_good"],
            ),
            # Fails volume
            _make_market(
                condition_id="high_vol",
                volume=50000,
                created_at=now,
                clob_token_ids=["tok_hv"],
            ),
            # Fails age
            _make_market(
                condition_id="old_mkt",
                volume=5000,
                created_at=old,
                clob_token_ids=["tok_old"],
            ),
            # Fails spread
            _make_market(
                condition_id="tight_spread",
                volume=5000,
                created_at=now,
                clob_token_ids=["tok_ts"],
            ),
        ]
        spreads = {
            "tok_good": 0.10,
            "tok_hv": 0.10,
            "tok_old": 0.10,
            "tok_ts": 0.01,
        }

        result = filter_opportunities(
            markets=markets,
            spreads=spreads,
            max_volume=10000,
            min_spread=0.05,
            max_age_hours=48,
        )

        ids = [m["conditionId"] for m in result]
        assert ids == ["good"]


class TestEmptyResult:
    """When no markets meet all criteria, return an empty list."""

    def test_empty_result_when_no_matches(self):
        from polymarket_bot.cogs.opportunities import filter_opportunities

        now = datetime.now(timezone.utc).isoformat()
        markets = [
            _make_market(condition_id="a", volume=50000, created_at=now),
        ]
        spreads = {"token_1": 0.01}

        result = filter_opportunities(
            markets=markets,
            spreads=spreads,
            max_volume=10000,
            min_spread=0.05,
            max_age_hours=48,
        )

        assert result == []


class TestMarketLevelNotEventLevel:
    """Opportunities should filter each market individually, not group by event."""

    def test_same_event_markets_filtered_independently(self):
        """Two markets sharing an event slug should pass or fail filters
        based on their own volume/age/spread, not the event's aggregate."""
        from polymarket_bot.cogs.opportunities import filter_opportunities

        now = datetime.now(timezone.utc).isoformat()

        # Market A: low volume, wide spread — should pass
        mkt_a = _make_market(
            condition_id="mA",
            question="Ceasefire before GTA VI?",
            volume=5000,
            created_at=now,
            clob_token_ids=["tok_a"],
        )
        mkt_a["events"] = [{"slug": "what-will-happen-before-gta-vi"}]

        # Market B: high volume, same event — should fail volume filter
        mkt_b = _make_market(
            condition_id="mB",
            question="New album before GTA VI?",
            volume=100000,
            created_at=now,
            clob_token_ids=["tok_b"],
        )
        mkt_b["events"] = [{"slug": "what-will-happen-before-gta-vi"}]

        spreads = {"tok_a": 0.10, "tok_b": 0.10}

        result = filter_opportunities(
            markets=[mkt_a, mkt_b],
            spreads=spreads,
            max_volume=10000,
            min_spread=0.05,
            max_age_hours=48,
        )

        ids = [m["conditionId"] for m in result]
        assert "mA" in ids, "Low-volume market should pass even though sibling has high volume"
        assert "mB" not in ids, "High-volume market should fail even though sibling has low volume"

    def test_each_market_uses_own_token_spread(self):
        """Markets in the same event should use their own token's spread,
        not a shared or averaged spread."""
        from polymarket_bot.cogs.opportunities import filter_opportunities

        now = datetime.now(timezone.utc).isoformat()

        mkt_wide = _make_market(
            condition_id="wide_spread",
            volume=5000,
            created_at=now,
            clob_token_ids=["tok_wide"],
        )
        mkt_wide["events"] = [{"slug": "shared-event"}]

        mkt_tight = _make_market(
            condition_id="tight_spread",
            volume=5000,
            created_at=now,
            clob_token_ids=["tok_tight"],
        )
        mkt_tight["events"] = [{"slug": "shared-event"}]

        spreads = {"tok_wide": 0.15, "tok_tight": 0.01}

        result = filter_opportunities(
            markets=[mkt_wide, mkt_tight],
            spreads=spreads,
            max_volume=10000,
            min_spread=0.05,
            max_age_hours=48,
        )

        ids = [m["conditionId"] for m in result]
        assert "wide_spread" in ids
        assert "tight_spread" not in ids


# ---------------------------------------------------------------------------
# Integration tests — real API calls
# ---------------------------------------------------------------------------


class TestFetchRecentMarkets:
    """Fetch recent markets from the Gamma API and verify shape."""

    async def test_fetch_recent_markets(self, session: aiohttp.ClientSession):
        async with session.get(
            f"{GAMMA_API_URL}/markets",
            params={
                "limit": 10,
                "active": "true",
                "closed": "false",
                "order": "startDate",
                "ascending": "false",
            },
        ) as resp:
            assert resp.status == 200
            markets = await resp.json()

        assert isinstance(markets, list)
        assert len(markets) > 0

        for market in markets:
            # Must have a volume or liquidity field for filtering
            has_volume = any(market.get(f) is not None for f in ("volume", "volumeNum", "liquidityNum", "liquidity"))
            assert has_volume, f"Market {market.get('conditionId')} has no volume/liquidity field"
            # Must have at least one date field for age filtering
            has_date = any(market.get(f) for f in ("startDate", "createdAt", "created_at"))
            assert has_date, f"Market {market.get('conditionId')} has no date field"


class TestFetchSpreadForRealToken:
    """Fetch spread for a real token from the CLOB API."""

    async def test_fetch_spread_for_real_token(self, session: aiohttp.ClientSession, token_id: str):
        async with session.get(f"{CLOB_API_URL}/spread", params={"token_id": token_id}) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "spread" in data


class TestScanReturnsCorrectType:
    """Run the full scan function against real APIs."""

    async def test_scan_returns_list(self, session: aiohttp.ClientSession):
        from polymarket_bot.cogs.opportunities import scan_opportunities

        result = await scan_opportunities(
            session=session,
            gamma_url=GAMMA_API_URL,
            clob_url=CLOB_API_URL,
            max_volume=10000,
            min_spread=0.05,
        )
        assert isinstance(result, list)
