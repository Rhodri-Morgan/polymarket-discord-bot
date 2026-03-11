"""Tests for the store module — JSON file I/O with atomic writes."""

import pytest

from polymarket_bot import store


@pytest.fixture(autouse=True)
def _use_tmp_data_dir(tmp_path, monkeypatch):
    """Point DATA_DIR at a temporary directory for every test."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


# --- load() ---


async def test_load_returns_empty_dict_when_file_missing(tmp_path):
    result = await store.load("nonexistent")
    assert result == {}


async def test_load_returns_empty_dict_when_file_empty(tmp_path):
    (tmp_path / "empty.json").write_text("")
    result = await store.load("empty")
    assert result == {}


# --- save() then load() round-trip ---


async def test_round_trip_simple_dict(tmp_path):
    data = {"seen_ids": ["a", "b", "c"], "last_check": "2026-03-07T14:00:00Z"}
    await store.save("seen_markets", data)
    loaded = await store.load("seen_markets")
    assert loaded == data


async def test_round_trip_nested_data_with_lists(tmp_path):
    data = {
        "snapshots": {
            "2026-03-07T13:00:00Z": {"market-1": {"question": "Will X happen?", "volume": 150000}},
            "2026-03-07T14:00:00Z": {"market-1": {"question": "Will X happen?", "volume": 160000}},
        },
        "tags": ["politics", "sports"],
    }
    await store.save("volume_snapshots", data)
    loaded = await store.load("volume_snapshots")
    assert loaded == data


# --- save() overwrites ---


async def test_save_overwrites_existing_file(tmp_path):
    await store.save("state", {"version": 1})
    await store.save("state", {"version": 2, "extra": True})
    loaded = await store.load("state")
    assert loaded == {"version": 2, "extra": True}


# --- no temp files left behind ---


async def test_no_temp_files_left_after_save(tmp_path):
    await store.save("clean", {"key": "value"})
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == "clean.json"


# --- directory creation ---


async def test_save_creates_data_directory_if_missing(tmp_path, monkeypatch):
    nested = tmp_path / "sub" / "dir"
    monkeypatch.setattr(store, "DATA_DIR", nested)
    await store.save("test", {"ok": True})
    loaded = await store.load("test")
    assert loaded == {"ok": True}
