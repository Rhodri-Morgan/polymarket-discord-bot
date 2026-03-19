# Polymarket Gamma API

Base URL: `https://gamma-api.polymarket.com`

The Gamma API is the primary data source. It is a public REST API with no authentication required.

## Endpoints Used

### `GET /events`

Returns event objects with nested market arrays.

**Common query parameters:**

| Parameter        | Type   | Notes                                      |
| ---------------- | ------ | ------------------------------------------ |
| `active`         | string | `"true"` / `"false"`                       |
| `closed`         | string | `"true"` / `"false"`                       |
| `neg_risk`       | string | `"true"` — server-side filter does NOT work reliably; client-side filtering required |
| `start_date_min` | string | ISO 8601, e.g. `"2025-01-01T00:00:00Z"`   |
| `order`          | string | Field to sort by (`"volume"`, `"liquidity"`) |
| `ascending`      | string | `"true"` / `"false"`                       |
| `limit`          | int    | Page size (max 100)                        |
| `offset`         | int    | Pagination offset                          |

## Pagination Pattern

All cogs use the same offset-based pagination loop:

```python
all_items: list[dict] = []
offset = 0
page_size = 100
while True:
    params = {..., "limit": page_size, "offset": offset}
    async with session.get(f"{gamma_url}/events", params=params) as resp:
        if resp.status != 200:
            break
        page = await resp.json()
    if not page:
        break
    all_items.extend(page)
    if len(all_items) >= 500 or len(page) < page_size:
        break
    offset += page_size
```

A hard cap bounds memory and response time — see the cog source for the current value.

## Field Types (Gotchas)

The API returns some fields as strings that look like numbers or JSON. Mocks and parsing code must match these types exactly:

| Field             | Type            | Example                          |
| ----------------- | --------------- | -------------------------------- |
| `volume`          | string          | `"1234567.89"`                   |
| `liquidity`       | string          | `"50000.0"`                      |
| `outcomePrices`   | JSON string     | `"[\"0.65\",\"0.35\"]"`         |
| `clobTokenIds`    | JSON string     | `"[\"123\",\"456\"]"`           |
| `outcomes`        | JSON string     | `"[\"Yes\",\"No\"]"`            |
| `negRisk`         | boolean         | `true` (native, not string)      |
| `active`          | boolean         | `true`                           |
| `closed`          | boolean         | `false`                          |
| `startDate`       | ISO 8601 string | `"2025-03-01T00:00:00Z"`        |
| `tags`            | array of objects| `[{"label": "Politics"}]`        |

## negRisk Events

negRisk (negative risk) events are multi-outcome markets where buying YES on all outcomes guarantees a $1.00 payout. This is the basis for the mispriced markets arbitrage detector.

**Key behaviours:**
- `neg_risk=true` query parameter exists but does **not** reliably filter results server-side. Always filter `event["negRisk"] is True` client-side.
- The API returns a mix of negRisk true/false events; the majority are negRisk.
- YES price sums on negRisk events show extreme variability — some are structurally far from 1.0 (many low-probability outcomes, missing "Other" bucket). A max deviation threshold in the mispriced markets cog filters out structural noise from genuine arbitrage.
