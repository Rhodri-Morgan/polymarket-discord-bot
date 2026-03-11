"""Tests for the trending events cog — filtering and ranking logic."""

from datetime import datetime, timedelta, timezone

from polymarket_bot.cogs.trending_events import (
    _has_excluded_tag,
    _volume_velocity,
)


def _make_event(
    id_: str,
    title: str = "Test Event",
    volume: float = 10000,
    tags: list[str] | None = None,
    age_hours: float = 12,
) -> dict:
    """Return an event dict matching the Gamma API shape."""
    created = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    tag_dicts = [{"label": t} for t in (tags or ["Politics"])]
    return {
        "id": id_,
        "title": title,
        "slug": f"test-event-{id_}",
        "volume": volume,
        "active": True,
        "closed": False,
        "startDate": created,
        "createdAt": created,
        "tags": tag_dicts,
        "markets": [
            {
                "id": f"{id_}_m1",
                "question": f"{title} - Yes/No",
                "slug": f"test-event-{id_}-yes-no",
                "volume": str(volume),
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.65", "0.35"]',
            }
        ],
    }


# ---------------------------------------------------------------------------
# Tag exclusion tests
# ---------------------------------------------------------------------------


def test_sports_tag_excluded():
    event = _make_event("1", tags=["Sports", "NBA"])
    assert _has_excluded_tag(event) is True


def test_crypto_tag_excluded():
    event = _make_event("1", tags=["Crypto", "Finance"])
    assert _has_excluded_tag(event) is True


def test_weather_tag_excluded():
    event = _make_event("1", tags=["Weather", "Recurring"])
    assert _has_excluded_tag(event) is True


def test_esports_tag_excluded():
    event = _make_event("1", tags=["Esports", "counter strike 2", "Games"])
    assert _has_excluded_tag(event) is True


def test_politics_tag_not_excluded():
    event = _make_event("1", tags=["Politics", "Elections"])
    assert _has_excluded_tag(event) is False


def test_culture_tag_not_excluded():
    event = _make_event("1", tags=["Culture", "Movies"])
    assert _has_excluded_tag(event) is False


def test_no_tags_not_excluded():
    event = _make_event("1", tags=[])
    assert _has_excluded_tag(event) is False


def test_sublabel_without_parent_not_excluded():
    """Sublabels like NBA are not in the excluded set — we rely on the parent 'Sports' tag."""
    event = _make_event("1", tags=["NBA", "Basketball"])
    assert _has_excluded_tag(event) is False


def test_case_insensitive_exclusion():
    """Tag matching should be case-insensitive."""
    event = _make_event("1", tags=["SPORTS"])
    assert _has_excluded_tag(event) is True


# ---------------------------------------------------------------------------
# Volume velocity tests
# ---------------------------------------------------------------------------


def test_volume_velocity_basic():
    """Volume / age_hours gives correct velocity."""
    event = _make_event("1", volume=24000, age_hours=12)
    velocity = _volume_velocity(event)
    assert abs(velocity - 2000) < 10  # ~$2000/hr, small margin for test execution time


def test_volume_velocity_newer_event_ranks_higher():
    """A newer event with same volume should have higher velocity."""
    old_event = _make_event("1", volume=10000, age_hours=48)
    new_event = _make_event("2", volume=10000, age_hours=6)
    assert _volume_velocity(new_event) > _volume_velocity(old_event)


def test_volume_velocity_zero_volume():
    event = _make_event("1", volume=0, age_hours=12)
    assert _volume_velocity(event) == 0.0


def test_volume_velocity_very_new_event():
    """Events less than 6 minutes old should not divide by zero."""
    event = _make_event("1", volume=1000, age_hours=0.001)
    velocity = _volume_velocity(event)
    assert velocity > 0


def test_sorting_by_velocity():
    """Events should sort correctly by volume velocity."""
    events = [
        _make_event("slow", volume=50000, age_hours=48),  # ~1042/hr
        _make_event("hot", volume=20000, age_hours=3),  # ~6667/hr
        _make_event("medium", volume=30000, age_hours=12),  # ~2500/hr
    ]
    events.sort(key=_volume_velocity, reverse=True)
    # "hot" should be first (highest velocity), then "medium", then "slow"
    assert events[0]["id"] == "hot"
    assert events[1]["id"] == "medium"
    assert events[2]["id"] == "slow"
