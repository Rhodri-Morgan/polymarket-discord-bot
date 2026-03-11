"""Tests for shared formatting utilities — trending events display."""

from datetime import datetime, timedelta, timezone

from polymarket_bot.formatting import (
    _event_category_emoji,
    _format_age,
    _format_volume,
    format_trending_events,
    total_pages,
)


def _make_event(
    *,
    title: str = "Test Event",
    slug: str = "test-event",
    volume: float = 50000,
    tags: list[str] | None = None,
    age_hours: float = 12,
    num_markets: int = 2,
) -> dict:
    created = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    tag_dicts = [{"label": t} for t in (tags or ["Politics"])]
    return {
        "title": title,
        "slug": slug,
        "volume": volume,
        "startDate": created,
        "createdAt": created,
        "tags": tag_dicts,
        "markets": [{"id": f"m{i}"} for i in range(num_markets)],
    }


# ---------------------------------------------------------------------------
# _format_volume
# ---------------------------------------------------------------------------


class TestFormatVolume:
    def test_millions(self):
        assert _format_volume(2_500_000) == "$2.5M"

    def test_thousands(self):
        assert _format_volume(45_000) == "$45.0K"

    def test_small(self):
        assert _format_volume(999) == "$999"

    def test_zero(self):
        assert _format_volume(0) == "$0"

    def test_string_input(self):
        assert _format_volume("1500000") == "$1.5M"

    def test_invalid_input(self):
        assert _format_volume("not-a-number") == "$?"

    def test_none_input(self):
        assert _format_volume(None) == "$?"


# ---------------------------------------------------------------------------
# total_pages
# ---------------------------------------------------------------------------


class TestTotalPages:
    def test_zero_items(self):
        assert total_pages(0, 5) == 0

    def test_exact_fit(self):
        assert total_pages(10, 5) == 2

    def test_remainder(self):
        assert total_pages(11, 5) == 3

    def test_single_item(self):
        assert total_pages(1, 10) == 1


# ---------------------------------------------------------------------------
# _event_category_emoji
# ---------------------------------------------------------------------------


class TestEventCategoryEmoji:
    def test_politics(self):
        event = _make_event(tags=["Politics"])
        assert _event_category_emoji(event) == "\U0001f3db\ufe0f"

    def test_sports(self):
        event = _make_event(tags=["Sports"])
        assert _event_category_emoji(event) == "\u26bd"

    def test_unknown_tag_returns_default(self):
        event = _make_event(tags=["SomeRandomTag"])
        assert _event_category_emoji(event) == "\U0001f4ca"

    def test_no_tags(self):
        event = {"tags": []}
        assert _event_category_emoji(event) == "\U0001f4ca"

    def test_missing_tags_key(self):
        event = {}
        assert _event_category_emoji(event) == "\U0001f4ca"


# ---------------------------------------------------------------------------
# _format_age
# ---------------------------------------------------------------------------


class TestFormatAge:
    def test_less_than_one_hour(self):
        event = _make_event(age_hours=0.25)
        assert _format_age(event) == "<1h"

    def test_hours_only(self):
        event = _make_event(age_hours=5)
        assert _format_age(event) == "5h"

    def test_days_and_hours(self):
        event = _make_event(age_hours=30)
        assert _format_age(event) == "1d 6h"

    def test_exact_days(self):
        event = _make_event(age_hours=48)
        assert _format_age(event) == "2d"

    def test_missing_dates(self):
        event = {"title": "No dates"}
        assert _format_age(event) == "?"


# ---------------------------------------------------------------------------
# format_trending_events
# ---------------------------------------------------------------------------


class TestFormatTrendingEvents:
    def test_empty_list(self):
        embeds = format_trending_events([])
        assert len(embeds) == 1
        assert "No trending events" in (embeds[0].description or "")

    def test_single_event(self):
        events = [_make_event(title="Hot Event", slug="hot-event")]
        embeds = format_trending_events(events, page=0, per_page=10)
        assert len(embeds) == 1
        assert len(embeds[0].fields) == 1
        assert "Hot Event" in embeds[0].fields[0].value
        assert "polymarket.com" in embeds[0].fields[0].value

    def test_pagination_footer(self):
        events = [_make_event(title=f"Event {i}", slug=f"event-{i}") for i in range(25)]
        embeds = format_trending_events(events, page=0, per_page=10)
        footer = embeds[0].footer.text if embeds[0].footer else ""
        assert "1" in footer
        assert "10" in footer
        assert "25" in footer

    def test_page_two(self):
        events = [_make_event(title=f"Event {i}", slug=f"event-{i}") for i in range(25)]
        embeds = format_trending_events(events, page=1, per_page=10)
        assert len(embeds[0].fields) == 10
        footer = embeds[0].footer.text if embeds[0].footer else ""
        assert "11" in footer
        assert "20" in footer

    def test_last_partial_page(self):
        events = [_make_event(title=f"Event {i}", slug=f"event-{i}") for i in range(23)]
        embeds = format_trending_events(events, page=2, per_page=10)
        assert len(embeds[0].fields) == 3

    def test_event_without_slug(self):
        events = [_make_event(title="No Slug")]
        events[0]["slug"] = ""
        embeds = format_trending_events(events)
        # Should still render without a link
        assert "No Slug" in embeds[0].fields[0].value
        assert "polymarket.com" not in embeds[0].fields[0].value

    def test_volume_and_age_in_field(self):
        events = [_make_event(volume=1_500_000, age_hours=6)]
        embeds = format_trending_events(events)
        value = embeds[0].fields[0].value
        assert "$1.5M" in value
        assert "6h" in value

    def test_market_count_in_field(self):
        events = [_make_event(num_markets=5)]
        embeds = format_trending_events(events)
        value = embeds[0].fields[0].value
        assert "5" in value
