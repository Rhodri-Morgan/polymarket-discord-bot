"""Tests for the mispriced markets cog — arbitrage detection logic."""

import json

import pytest

from polymarket_bot.cogs.mispriced_markets import (
    MAX_DEVIATION,
    MIN_EVENT_LIQUIDITY,
    MIN_MARKET_LIQUIDITY,
    MAX_RESULTS,
    _parse_yes_price,
    _event_price_sum,
    _event_deviation,
    _is_tradeable,
    rank_mispriced_events,
)


def _make_neg_risk_event(
    id_: str,
    title: str = "Who will win?",
    markets: list[dict] | None = None,
) -> dict:
    """Return a negRisk event dict matching the Gamma API shape.

    Each market in the markets list should have:
      - yes_price: float
      - liquidity: float (default 50000)
      - active: bool (default True)
      - closed: bool (default False)
      - group_title: str (default "Outcome N")
    """
    if markets is None:
        markets = [
            {"yes_price": 0.55, "liquidity": 50000},
            {"yes_price": 0.40, "liquidity": 50000},
        ]

    market_dicts = []
    for i, m in enumerate(markets):
        yes = m.get("yes_price", 0.5)
        no = round(1.0 - yes, 4)
        liq = m.get("liquidity", 50000)
        active = m.get("active", True)
        closed = m.get("closed", False)
        group_title = m.get("group_title", f"Outcome {i + 1}")
        market_dicts.append(
            {
                "id": f"{id_}_m{i}",
                "question": f"{title} - {group_title}",
                "slug": f"test-{id_}-m{i}",
                "groupItemTitle": group_title,
                "outcomes": json.dumps(["Yes", "No"]),
                "outcomePrices": json.dumps([str(yes), str(no)]),
                "volume": str(liq * 10),
                "liquidity": str(liq),
                "liquidityNum": liq,
                "active": active,
                "closed": closed,
            }
        )

    total_liq = sum(m.get("liquidity", 50000) for m in markets)
    return {
        "id": id_,
        "title": title,
        "slug": f"test-event-{id_}",
        "active": True,
        "closed": False,
        "negRisk": True,
        "liquidity": total_liq,
        "markets": market_dicts,
    }


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------


def test_parse_yes_price_normal():
    market = {"outcomePrices": json.dumps(["0.65", "0.35"])}
    assert _parse_yes_price(market) == pytest.approx(0.65)


def test_parse_yes_price_missing():
    assert _parse_yes_price({}) == 0.0


def test_parse_yes_price_empty_list():
    market = {"outcomePrices": "[]"}
    assert _parse_yes_price(market) == 0.0


def test_parse_yes_price_invalid_json():
    market = {"outcomePrices": "not json"}
    assert _parse_yes_price(market) == 0.0


# ---------------------------------------------------------------------------
# Event price sum
# ---------------------------------------------------------------------------


def test_event_price_sum_two_markets():
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 50000},
            {"yes_price": 0.35, "liquidity": 50000},
        ],
    )
    assert _event_price_sum(event) == pytest.approx(0.95)


def test_event_price_sum_three_markets():
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.50, "liquidity": 50000},
            {"yes_price": 0.30, "liquidity": 50000},
            {"yes_price": 0.25, "liquidity": 50000},
        ],
    )
    assert _event_price_sum(event) == pytest.approx(1.05)


def test_event_price_sum_skips_closed_markets():
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 50000},
            {"yes_price": 0.35, "liquidity": 50000, "closed": True},
            {"yes_price": 0.30, "liquidity": 50000},
        ],
    )
    assert _event_price_sum(event) == pytest.approx(0.90)


def test_event_price_sum_skips_inactive_markets():
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 50000},
            {"yes_price": 0.35, "liquidity": 50000, "active": False},
        ],
    )
    assert _event_price_sum(event) == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# Deviation
# ---------------------------------------------------------------------------


def test_deviation_underpriced():
    """Sum < 1.0 means you can buy all YES cheaply."""
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.45, "liquidity": 50000},
            {"yes_price": 0.45, "liquidity": 50000},
        ],
    )
    assert _event_deviation(event) == pytest.approx(0.10)


def test_deviation_overpriced():
    """Sum > 1.0 means YES is overpriced."""
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.55, "liquidity": 50000},
            {"yes_price": 0.55, "liquidity": 50000},
        ],
    )
    assert _event_deviation(event) == pytest.approx(0.10)


def test_deviation_perfectly_priced():
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 50000},
            {"yes_price": 0.40, "liquidity": 50000},
        ],
    )
    assert _event_deviation(event) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Tradeability / liquidity filters
# ---------------------------------------------------------------------------


def test_tradeable_event_passes():
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 50000},
            {"yes_price": 0.35, "liquidity": 50000},
        ],
    )
    assert _is_tradeable(event) is True


def test_not_tradeable_low_total_liquidity():
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 1000},
            {"yes_price": 0.35, "liquidity": 1000},
        ],
    )
    assert _is_tradeable(event) is False


def test_not_tradeable_one_market_illiquid():
    """If any active market has liquidity below threshold, event is not tradeable."""
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 50000},
            {"yes_price": 0.35, "liquidity": 100},
        ],
    )
    assert _is_tradeable(event) is False


def test_not_tradeable_single_market():
    """Need 2+ active markets for cross-outcome arbitrage."""
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 50000},
        ],
    )
    assert _is_tradeable(event) is False


def test_not_tradeable_non_neg_risk():
    """Non-negRisk events don't have mutually exclusive outcomes."""
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 50000},
            {"yes_price": 0.35, "liquidity": 50000},
        ],
    )
    event["negRisk"] = False
    assert _is_tradeable(event) is False


def test_closed_markets_excluded_from_liquidity_check():
    """Closed markets shouldn't count toward active market minimum."""
    event = _make_neg_risk_event(
        "1",
        markets=[
            {"yes_price": 0.60, "liquidity": 50000},
            {"yes_price": 0.35, "liquidity": 50000, "closed": True},
        ],
    )
    # Only 1 active market -> not tradeable
    assert _is_tradeable(event) is False


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_rank_sorts_by_deviation_descending():
    events = [
        _make_neg_risk_event(
            "small",
            markets=[
                {"yes_price": 0.51, "liquidity": 50000},
                {"yes_price": 0.47, "liquidity": 50000},
            ],
        ),  # deviation 0.02
        _make_neg_risk_event(
            "big",
            markets=[
                {"yes_price": 0.46, "liquidity": 50000},
                {"yes_price": 0.46, "liquidity": 50000},
            ],
        ),  # deviation 0.08
        _make_neg_risk_event(
            "medium",
            markets=[
                {"yes_price": 0.52, "liquidity": 50000},
                {"yes_price": 0.52, "liquidity": 50000},
            ],
        ),  # deviation 0.04
    ]
    ranked = rank_mispriced_events(events)
    assert ranked[0]["id"] == "big"
    assert ranked[1]["id"] == "medium"
    assert ranked[2]["id"] == "small"


def test_rank_filters_untradeable():
    events = [
        _make_neg_risk_event(
            "good",
            markets=[
                {"yes_price": 0.47, "liquidity": 50000},
                {"yes_price": 0.47, "liquidity": 50000},
            ],
        ),  # deviation 0.06
        _make_neg_risk_event(
            "illiquid",
            markets=[
                {"yes_price": 0.47, "liquidity": 100},
                {"yes_price": 0.47, "liquidity": 100},
            ],
        ),
    ]
    ranked = rank_mispriced_events(events)
    assert len(ranked) == 1
    assert ranked[0]["id"] == "good"


def test_rank_filters_structural_deviation():
    """Deviations > MAX_DEVIATION are structural, not real arbs."""
    events = [
        _make_neg_risk_event(
            "real_arb",
            markets=[
                {"yes_price": 0.47, "liquidity": 50000},
                {"yes_price": 0.47, "liquidity": 50000},
            ],
        ),  # deviation 0.06 — real
        _make_neg_risk_event(
            "structural",
            markets=[
                {"yes_price": 0.30, "liquidity": 50000},
                {"yes_price": 0.30, "liquidity": 50000},
            ],
        ),  # deviation 0.40 — structural
    ]
    ranked = rank_mispriced_events(events)
    assert len(ranked) == 1
    assert ranked[0]["id"] == "real_arb"


def test_rank_filters_zero_deviation():
    """Perfectly priced events should be excluded."""
    events = [
        _make_neg_risk_event(
            "perfect",
            markets=[
                {"yes_price": 0.60, "liquidity": 50000},
                {"yes_price": 0.40, "liquidity": 50000},
            ],
        ),
    ]
    ranked = rank_mispriced_events(events)
    assert len(ranked) == 0


def test_rank_limits_to_max_results():
    events = [
        _make_neg_risk_event(
            str(i),
            markets=[
                {"yes_price": 0.48, "liquidity": 50000},
                {"yes_price": 0.48, "liquidity": 50000},
            ],
        )
        for i in range(150)
    ]
    ranked = rank_mispriced_events(events)
    assert len(ranked) <= MAX_RESULTS


def test_rank_empty_input():
    assert rank_mispriced_events([]) == []


def test_rank_no_tradeable_events():
    events = [
        _make_neg_risk_event(
            "1",
            markets=[
                {"yes_price": 0.50, "liquidity": 100},
                {"yes_price": 0.50, "liquidity": 100},
            ],
        ),
    ]
    assert rank_mispriced_events(events) == []
