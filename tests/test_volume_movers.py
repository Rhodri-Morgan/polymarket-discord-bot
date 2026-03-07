"""Tests for the Volume Movers cog — snapshot logic, report generation, and API integration."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import aiohttp
import pytest

from polymarket_bot import store


@pytest.fixture(autouse=True)
def _use_tmp_data_dir(tmp_path, monkeypatch):
    """Point DATA_DIR at a temporary directory for every test."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


def _utc_iso(dt: datetime) -> str:
    """Format a datetime as an ISO string matching snapshot keys."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FakeResponse:
    """Mimics aiohttp.ClientResponse as an async context manager."""

    def __init__(self, data: list[dict], status: int = 200):
        self._data = data
        self.status = status

    async def json(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_fake_session(markets: list[dict]):
    """Create a fake aiohttp session that returns *markets* from any GET."""

    class FakeSession:
        @staticmethod
        def get(url, **kwargs):
            return _FakeResponse(markets)

    return FakeSession()


# ---------------------------------------------------------------------------
# Snapshot logic
# ---------------------------------------------------------------------------


async def test_cold_start_takes_snapshot_no_report(tmp_path):
    """When volume_snapshots.json is missing, taking a snapshot should create
    the file with one entry and return None (no report)."""
    from polymarket_bot.cogs.volume_movers import take_snapshot, generate_report

    # Mock markets match real Gamma API shape: volume is a string, id is a string
    fake_markets = [
        {"id": "m1", "question": "Will X happen?", "volume": "1000", "volumeNum": 1000},
        {"id": "m2", "question": "Will Y happen?", "volume": "2000", "volumeNum": 2000},
    ]

    await take_snapshot(_make_fake_session(fake_markets), "https://fake-gamma.example.com")

    data = await store.load("volume_snapshots")
    assert "snapshots" in data
    assert len(data["snapshots"]) == 1

    # With only one snapshot, report should be None
    report = await generate_report()
    assert report is None


async def test_snapshot_adds_to_existing(tmp_path):
    """Pre-populate with one snapshot. Take another. Verify two snapshots."""
    from polymarket_bot.cogs.volume_movers import take_snapshot

    now = _now()
    existing_ts = _utc_iso(now - timedelta(hours=1))
    await store.save(
        "volume_snapshots",
        {
            "snapshots": {
                existing_ts: {"m1": {"question": "Will X?", "volume": 1000}},
            }
        },
    )

    fake_markets = [
        {"id": "m1", "question": "Will X?", "volume": "1500", "volumeNum": 1500},
    ]

    await take_snapshot(_make_fake_session(fake_markets), "https://fake-gamma.example.com")

    data = await store.load("volume_snapshots")
    assert len(data["snapshots"]) == 2


async def test_snapshot_prunes_old_entries(tmp_path):
    """Pre-populate with 30 hourly snapshots. Take a new one. Only last 25h kept."""
    from polymarket_bot.cogs.volume_movers import take_snapshot

    now = _now()
    snapshots = {}
    for i in range(30):
        ts = _utc_iso(now - timedelta(hours=30 - i))
        snapshots[ts] = {"m1": {"question": "Will X?", "volume": 1000 + i}}
    await store.save("volume_snapshots", {"snapshots": snapshots})

    fake_markets = [
        {"id": "m1", "question": "Will X?", "volume": "2000", "volumeNum": 2000},
    ]

    await take_snapshot(_make_fake_session(fake_markets), "https://fake-gamma.example.com")

    data = await store.load("volume_snapshots")
    # Should have pruned to at most 25h worth + 1 new = at most 26,
    # but the pruning removes anything older than 25h from now.
    for ts_str in data["snapshots"]:
        ts_dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        age = now - ts_dt
        assert age <= timedelta(hours=25, minutes=5)  # small tolerance


# ---------------------------------------------------------------------------
# Report logic
# ---------------------------------------------------------------------------


async def test_report_with_no_snapshots_returns_none(tmp_path):
    """No state file. Report should return None."""
    from polymarket_bot.cogs.volume_movers import generate_report

    report = await generate_report()
    assert report is None


async def test_report_with_one_snapshot_returns_none(tmp_path):
    """Only one snapshot exists. Not enough data. Return None."""
    from polymarket_bot.cogs.volume_movers import generate_report

    now = _now()
    await store.save(
        "volume_snapshots",
        {
            "snapshots": {
                _utc_iso(now): {"m1": {"question": "Will X?", "volume": 1000}},
            }
        },
    )
    report = await generate_report()
    assert report is None


async def test_report_with_two_snapshots_24h_apart(tmp_path):
    """Two snapshots 24h apart. Verify ranking by absolute and percentage increase."""
    from polymarket_bot.cogs.volume_movers import generate_report

    now = _now()
    old_ts = _utc_iso(now - timedelta(hours=24))
    new_ts = _utc_iso(now)

    await store.save(
        "volume_snapshots",
        {
            "snapshots": {
                old_ts: {
                    "mA": {"question": "Market A", "volume": 1000},
                    "mB": {"question": "Market B", "volume": 500},
                },
                new_ts: {
                    "mA": {"question": "Market A", "volume": 5000},
                    "mB": {"question": "Market B", "volume": 2000},
                },
            }
        },
    )

    report = await generate_report()
    assert report is not None

    # Absolute: A increased by 4000, B by 1500 -> A first
    assert report["absolute"][0]["market_id"] == "mA"
    assert report["absolute"][0]["abs_change"] == 4000
    assert report["absolute"][1]["market_id"] == "mB"
    assert report["absolute"][1]["abs_change"] == 1500

    # Percentage: B went from 500->2000 = 300%, A went from 1000->5000 = 400%
    # Actually: A = (5000-1000)/1000 = 400%, B = (2000-500)/500 = 300% -> A first
    assert report["percentage"][0]["market_id"] == "mA"
    assert report["percentage"][0]["pct_change"] == pytest.approx(400.0)
    assert report["percentage"][1]["market_id"] == "mB"
    assert report["percentage"][1]["pct_change"] == pytest.approx(300.0)


async def test_report_finds_closest_snapshot_to_24h(tmp_path):
    """With snapshots at t-23h, t-25h, and t-now, should compare against t-23h."""
    from polymarket_bot.cogs.volume_movers import generate_report

    now = _now()
    ts_25h = _utc_iso(now - timedelta(hours=25, minutes=30))
    ts_23h = _utc_iso(now - timedelta(hours=23))
    ts_now = _utc_iso(now)

    await store.save(
        "volume_snapshots",
        {
            "snapshots": {
                ts_25h: {
                    "mA": {"question": "Market A", "volume": 100},
                },
                ts_23h: {
                    "mA": {"question": "Market A", "volume": 200},
                },
                ts_now: {
                    "mA": {"question": "Market A", "volume": 1000},
                },
            }
        },
    )

    report = await generate_report()
    assert report is not None

    # Compared against t-23h (volume 200), not t-25h (volume 100)
    assert report["absolute"][0]["abs_change"] == 800  # 1000 - 200
    assert report["absolute"][0]["old_volume"] == 200


async def test_report_handles_new_market_in_latest_snapshot(tmp_path):
    """Market appears only in latest snapshot. Treat old volume as 0."""
    from polymarket_bot.cogs.volume_movers import generate_report

    now = _now()
    old_ts = _utc_iso(now - timedelta(hours=24))
    new_ts = _utc_iso(now)

    await store.save(
        "volume_snapshots",
        {
            "snapshots": {
                old_ts: {
                    "mA": {"question": "Market A", "volume": 1000},
                },
                new_ts: {
                    "mA": {"question": "Market A", "volume": 2000},
                    "mNew": {"question": "Brand New Market", "volume": 500},
                },
            }
        },
    )

    report = await generate_report()
    assert report is not None

    # mNew should be in the report with old_volume=0
    all_ids = [entry["market_id"] for entry in report["absolute"]]
    assert "mNew" in all_ids

    new_entry = [e for e in report["absolute"] if e["market_id"] == "mNew"][0]
    assert new_entry["abs_change"] == 500
    assert new_entry["old_volume"] == 0


async def test_report_handles_disappeared_market(tmp_path):
    """Market in old snapshot but not latest. Excluded from report."""
    from polymarket_bot.cogs.volume_movers import generate_report

    now = _now()
    old_ts = _utc_iso(now - timedelta(hours=24))
    new_ts = _utc_iso(now)

    await store.save(
        "volume_snapshots",
        {
            "snapshots": {
                old_ts: {
                    "mA": {"question": "Market A", "volume": 1000},
                    "mGone": {"question": "Gone Market", "volume": 5000},
                },
                new_ts: {
                    "mA": {"question": "Market A", "volume": 2000},
                },
            }
        },
    )

    report = await generate_report()
    assert report is not None

    all_ids = [entry["market_id"] for entry in report["absolute"]]
    assert "mGone" not in all_ids


async def test_tracks_individual_markets_within_same_event(tmp_path):
    """Two markets in the same event should have independent volume tracking.

    Verifies that volume movers operates at the market level — each market ID
    gets its own volume entry in snapshots and its own row in the report.
    """
    from polymarket_bot.cogs.volume_movers import generate_report

    now = _now()
    old_ts = _utc_iso(now - timedelta(hours=24))
    new_ts = _utc_iso(now)

    # Two markets belonging to the same event, with different volume changes
    await store.save(
        "volume_snapshots",
        {
            "snapshots": {
                old_ts: {
                    "mA": {"question": "Ceasefire before GTA VI?", "volume": 1000},
                    "mB": {"question": "New album before GTA VI?", "volume": 2000},
                },
                new_ts: {
                    "mA": {"question": "Ceasefire before GTA VI?", "volume": 8000},
                    "mB": {"question": "New album before GTA VI?", "volume": 2500},
                },
            }
        },
    )

    report = await generate_report()
    assert report is not None

    # Both individual markets should appear in the report separately
    abs_ids = [e["market_id"] for e in report["absolute"]]
    assert "mA" in abs_ids
    assert "mB" in abs_ids

    # mA increased by 7000, mB by 500 — they are tracked independently
    entry_a = [e for e in report["absolute"] if e["market_id"] == "mA"][0]
    entry_b = [e for e in report["absolute"] if e["market_id"] == "mB"][0]
    assert entry_a["abs_change"] == 7000
    assert entry_b["abs_change"] == 500

    # mA should rank higher than mB by absolute change
    assert abs_ids.index("mA") < abs_ids.index("mB")


async def test_snapshot_stores_per_market_id_not_per_event(tmp_path):
    """Verify that take_snapshot keys data by individual market ID."""
    from polymarket_bot.cogs.volume_movers import take_snapshot

    # Two markets that would share an event in real life
    fake_markets = [
        {"id": "m1", "question": "Ceasefire before GTA VI?", "volume": "5000", "volumeNum": 5000},
        {"id": "m2", "question": "New album before GTA VI?", "volume": "3000", "volumeNum": 3000},
    ]

    await take_snapshot(_make_fake_session(fake_markets), "https://fake-gamma.example.com")

    data = await store.load("volume_snapshots")
    snapshot = next(iter(data["snapshots"].values()))

    # Both market IDs should be separate keys in the snapshot
    assert "m1" in snapshot
    assert "m2" in snapshot
    assert snapshot["m1"]["volume"] == 5000.0
    assert snapshot["m2"]["volume"] == 3000.0


# ---------------------------------------------------------------------------
# Integration — real API call
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_snapshot_captures_real_api_data(tmp_path):
    """Make a real HTTP call to the Gamma API, take a snapshot, verify data."""
    from polymarket_bot.cogs.volume_movers import take_snapshot

    async with aiohttp.ClientSession() as session:
        await take_snapshot(session, "https://gamma-api.polymarket.com")

    data = await store.load("volume_snapshots")
    assert "snapshots" in data
    assert len(data["snapshots"]) == 1

    # Get the single snapshot
    snapshot = next(iter(data["snapshots"].values()))
    assert len(snapshot) > 0

    # Verify structure: each entry has question and volume
    first_market = next(iter(snapshot.values()))
    assert "question" in first_market
    assert "volume" in first_market
    assert isinstance(first_market["volume"], (int, float))
