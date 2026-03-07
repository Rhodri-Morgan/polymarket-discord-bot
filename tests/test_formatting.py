"""Tests for the shared market embed formatter."""

import json
from datetime import datetime, timezone

import pytest

from polymarket_bot import market_url


def _make_market(
    *,
    id_: str = "123",
    question: str = "Will it rain?",
    slug: str = "will-it-rain",
    event_slug: str = "will-it-rain",
    volume: str = "50000.5",
    outcome_prices: list[str] | None = None,
    outcomes: list[str] | None = None,
) -> dict:
    """Build a mock market dict matching the real Gamma API shape."""
    if outcome_prices is None:
        outcome_prices = ["0.65", "0.35"]
    if outcomes is None:
        outcomes = ["Yes", "No"]
    return {
        "id": id_,
        "question": question,
        "slug": slug,
        "volume": volume,
        "volumeNum": float(volume),
        "outcomePrices": json.dumps(outcome_prices),
        "outcomes": json.dumps(outcomes),
        "events": [{"slug": event_slug}],
        "clobTokenIds": '["tok1", "tok2"]',
        "startDate": "2026-03-07T12:00:00Z",
    }


class TestFormatMarketEmbed:
    """Test the embed formatting for a single market."""

    def test_embed_contains_question_as_title_or_field(self):
        from polymarket_bot.formatting import format_market_embed

        market = _make_market(question="Will BTC hit 100k?")
        embed = format_market_embed(market)

        # Question should appear somewhere in the embed
        text = (embed.title or "") + "".join(f.name + f.value for f in embed.fields)
        assert "Will BTC hit 100k?" in text

    def test_embed_contains_volume(self):
        from polymarket_bot.formatting import format_market_embed

        market = _make_market(volume="1234567.89")
        embed = format_market_embed(market)

        text = "".join(f.value for f in embed.fields) + (embed.description or "")
        # Should format volume with $ and commas or similar
        assert "$" in text
        assert "1" in text  # at least part of the volume number

    def test_embed_contains_yes_no_percentages(self):
        from polymarket_bot.formatting import format_market_embed

        market = _make_market(outcome_prices=["0.72", "0.28"])
        embed = format_market_embed(market)

        text = "".join(f.value for f in embed.fields) + (embed.description or "")
        assert "72%" in text
        assert "28%" in text

    def test_embed_contains_market_link(self):
        from polymarket_bot.formatting import format_market_embed

        market = _make_market(slug="btc-100k", event_slug="btc-100k")
        embed = format_market_embed(market)

        all_text = (embed.title or "") + (embed.description or "") + (embed.url or "")
        all_text += "".join(f.value for f in embed.fields)
        assert "polymarket.com" in all_text


class TestFormatMarketList:
    """Test formatting a list of markets into paginated embeds."""

    def test_returns_list_of_embeds(self):
        from polymarket_bot.formatting import format_market_list

        markets = [_make_market(id_=str(i), question=f"Market {i}?") for i in range(3)]
        embeds = format_market_list(markets, page=0, per_page=5)
        assert isinstance(embeds, list)
        assert len(embeds) == 1  # all fit on one page

    def test_pagination_limits_results(self):
        from polymarket_bot.formatting import format_market_list

        markets = [_make_market(id_=str(i), question=f"Market {i}?") for i in range(12)]
        page0 = format_market_list(markets, page=0, per_page=5)
        page1 = format_market_list(markets, page=1, per_page=5)
        page2 = format_market_list(markets, page=2, per_page=5)

        # Page 0 and 1 have 5 markets each, page 2 has 2
        assert len(page0) == 1  # single embed with 5 fields
        assert len(page1) == 1
        assert len(page2) == 1

        # Check field counts reflect pagination
        assert len(page0[0].fields) == 5
        assert len(page1[0].fields) == 5
        assert len(page2[0].fields) == 2

    def test_page_footer_shows_position(self):
        from polymarket_bot.formatting import format_market_list

        markets = [_make_market(id_=str(i), question=f"Market {i}?") for i in range(12)]
        embeds = format_market_list(markets, page=0, per_page=5)

        footer_text = embeds[0].footer.text if embeds[0].footer else ""
        assert "1" in footer_text and "5" in footer_text
        assert "12" in footer_text

    def test_empty_market_list(self):
        from polymarket_bot.formatting import format_market_list

        embeds = format_market_list([], page=0, per_page=5)
        assert len(embeds) == 1
        assert "No markets" in (embeds[0].description or "")

    def test_markets_sorted_by_volume_descending(self):
        from polymarket_bot.formatting import format_market_list

        markets = [
            _make_market(id_="low", question="Low vol?", volume="1000"),
            _make_market(id_="high", question="High vol?", volume="999999"),
            _make_market(id_="mid", question="Mid vol?", volume="50000"),
        ]
        embeds = format_market_list(markets, page=0, per_page=5, sort="volume")

        # First field should be the highest volume market
        assert "High vol?" in embeds[0].fields[0].name
        assert "Low vol?" in embeds[0].fields[2].name


class TestParseOutcomes:
    """Test parsing of outcome prices from various API formats."""

    def test_json_string_prices(self):
        from polymarket_bot.formatting import parse_outcomes

        market = _make_market(
            outcomes=["Yes", "No"],
            outcome_prices=["0.65", "0.35"],
        )
        result = parse_outcomes(market)
        assert result == [("Yes", 65.0), ("No", 35.0)]

    def test_missing_prices_returns_empty(self):
        from polymarket_bot.formatting import parse_outcomes

        market = {"outcomes": '["Yes", "No"]'}
        result = parse_outcomes(market)
        assert result == []

    def test_multi_outcome_market(self):
        from polymarket_bot.formatting import parse_outcomes

        market = {
            "outcomes": json.dumps(["Trump", "Biden", "DeSantis"]),
            "outcomePrices": json.dumps(["0.45", "0.30", "0.25"]),
        }
        result = parse_outcomes(market)
        assert len(result) == 3
        assert result[0] == ("Trump", 45.0)
        assert result[1] == ("Biden", 30.0)
        assert result[2] == ("DeSantis", 25.0)


class TestTotalPages:
    """Test page count calculation."""

    def test_total_pages(self):
        from polymarket_bot.formatting import total_pages

        assert total_pages(0, 5) == 0
        assert total_pages(1, 5) == 1
        assert total_pages(5, 5) == 1
        assert total_pages(6, 5) == 2
        assert total_pages(12, 5) == 3
