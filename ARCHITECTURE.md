# Architecture

## System Overview

```
┌──────────────────────────────────────────────────────┐
│  EC2 Instance (deployed via Ansible)                 │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Docker: polymarket-bot                        │  │
│  │                                                │  │
│  │  ┌──────────────┐    ┌──────────────────────┐  │  │
│  │  │  Bot Process  │───▶│  Discord Gateway     │  │  │
│  │  │  (asyncio)   │    │  (WebSocket)         │  │  │
│  │  └──────┬───────┘    └──────────────────────┘  │  │
│  │         │                                      │  │
│  │         ├── Cog: polymarket.py (slash commands) │  │
│  │         ├── Cog: new_markets.py (hourly loop)  │  │
│  │         ├── Cog: volume_movers.py (hourly +    │  │
│  │         │        daily report)                  │  │
│  │         └── Cog: opportunities.py (hourly loop)│  │
│  │         │                                      │  │
│  │         ▼                                      │  │
│  │  ┌──────────────┐    ┌──────────────────────┐  │  │
│  │  │  store.py    │───▶│  /app/data/ (EBS)    │  │  │
│  │  │  (JSON I/O)  │    │  ├ seen_markets.json  │  │  │
│  │  └──────────────┘    │  └ volume_snapshots   │  │  │
│  │                      │    .json              │  │  │
│  │                      └──────────────────────┘  │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Mounts:                                             │
│    .env         → env vars (bot token, channel IDs)  │
│    ~/.aws       → read-only (AWS_PROFILE=RTM)        │
│    EBS volume   → /app/data (persistent state)       │
└──────────────────────────────────────────────────────┘

External APIs (public, no auth):
  ├── Gamma API  (gamma-api.polymarket.com) — markets, events, search
  └── CLOB API   (clob.polymarket.com)      — prices, spreads, order books
```

## Source Layout

```
src/polymarket_bot/
├── __main__.py          # Entry point: python -m polymarket_bot
├── bot.py               # PolymarketBot class — auto-loads cogs, syncs slash commands
├── config.py            # Settings dataclass, loaded from env vars
├── store.py             # JSON state file I/O (atomic writes, /app/data)
└── cogs/
    ├── polymarket.py    # Interactive slash commands (/markets, /ping)
    ├── new_markets.py   # Scheduled: hourly new market alerts
    ├── volume_movers.py # Scheduled: hourly snapshots + daily volume report
    └── opportunities.py # Scheduled: hourly low-liquidity market scan
```

## Cog Types

### Interactive Cogs

Standard slash commands that respond to user input. No background state.

- **polymarket.py** — `/markets [tag]`, `/ping`

### Scheduled Cogs

Background task loops using `discord.ext.tasks`. Each follows this pattern:

1. **`cog_load`** — check for existing state file. If missing/empty, run a silent bootstrap (see Cold Start below).
2. **`@tasks.loop(hours=N)`** — the main loop that runs on schedule.
3. **`@loop.before_loop`** — `await self.bot.wait_until_ready()` to avoid firing before the gateway is connected.
4. **Companion slash command** — manually trigger the loop logic on demand (e.g. `/new-markets`).

Scheduled cogs:

- **new_markets.py** — hourly, posts new markets to `ALERT_CHANNEL_ID`
- **volume_movers.py** — hourly snapshots, daily report to `VOLUME_REPORT_CHANNEL_ID`
- **opportunities.py** — hourly, posts low-liquidity opportunities to `OPPORTUNITY_CHANNEL_ID`

## Cold Start / Bootstrap

When the bot starts fresh (no state files on disk) or after a data wipe, each scheduled cog bootstraps itself silently on its first run:

### New Market Alerts

1. State file `seen_markets.json` is missing or empty.
2. Fetch all active markets from the Gamma API.
3. Write every market ID to `seen_markets.json`.
4. **Post nothing.** This seeds the baseline.
5. From the next hourly run onward, only markets that weren't in the initial set trigger alerts.

### Volume Movers

1. State file `volume_snapshots.json` is missing or empty.
2. Fetch all active markets and take an immediate volume snapshot.
3. Write the snapshot to `volume_snapshots.json`.
4. **No report is generated.** There's no comparison point yet.
5. Hourly snapshots continue accumulating. The first daily report fires once two snapshots exist that are ~24h apart.

### Opportunity Finder

- Stateless — no bootstrap needed. Works from the first run.

### After a Restart (State Files Exist)

If state files already exist on the EBS volume, cogs load them and continue from where they left off. No re-bootstrap, no duplicate alerts.

## Persistence Layer — store.py

All state lives as JSON files in a single directory on the EBS volume.

```python
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))

async def load(name: str) -> dict    # Returns {} if file missing/empty
async def save(name: str, data: dict) -> None  # Atomic write (tmp + rename)
```

### Atomic Writes

`save()` writes to a temporary file first, then renames it over the target. This prevents corruption if the process is killed mid-write. The rename is atomic on Linux/ext4 (the EBS filesystem).

### State Files

**`seen_markets.json`**

```json
{
  "seen_ids": ["market-id-1", "market-id-2"],
  "last_check": "2026-03-07T14:00:00Z"
}
```

- **Pruned each run:** IDs for markets that are no longer active get removed.

**`volume_snapshots.json`**

```json
{
  "snapshots": {
    "2026-03-07T13:00:00Z": {
      "market-id-1": {"question": "Will X happen?", "volume": 150000}
    },
    "2026-03-07T14:00:00Z": { ... }
  }
}
```

- **Pruned each write:** entries older than 25 hours are deleted. At most ~25 snapshots exist.

### Data Lifecycle

No manual cleanup needed. Each cog prunes its own state file on every write cycle:

- `seen_markets.json` drops inactive market IDs
- `volume_snapshots.json` drops snapshots older than 25h

To fully reset, delete the files from the EBS volume. The bot will re-bootstrap on next start.

## Polymarket APIs

Both APIs are public. No authentication, no wallet, no API keys required for read-only access.

### Gamma API (`https://gamma-api.polymarket.com`)

Market discovery and metadata.

| Endpoint              | Description                                                                    |
| --------------------- | ------------------------------------------------------------------------------ |
| `GET /markets`        | List markets. Params: `limit`, `active`, `closed`, `tag`, `order`, `ascending` |
| `GET /markets/{slug}` | Single market detail                                                           |
| `GET /public-search`  | Search markets by keyword                                                      |
| `GET /events`         | List events with filtering                                                     |

### CLOB API (`https://clob.polymarket.com`)

Live pricing and order book data.

| Endpoint                        | Description              |
| ------------------------------- | ------------------------ |
| `GET /price?token_id=`          | Price for a single token |
| `GET /midpoint?token_id=`       | Midpoint price           |
| `GET /spread?token_id=`         | Bid/ask spread           |
| `GET /book?token_id=`           | Full order book          |
| `GET /prices-history?token_id=` | Historical prices        |

## Test Strategy

This project follows strict test-driven development. **Tests are written before implementation.**

### Test Categories

#### 1. API Integration Tests (`tests/test_polymarket_api.py`)

Real HTTP calls to the public Polymarket APIs. Verify:

- Endpoints return 200 with expected data shapes
- Markets have required fields (`question`, `slug`, `volume`, `outcomes`, `active`)
- Filtering params work (`active`, `closed`, `limit`, `tag`)
- CLOB endpoints return price/spread/book data in expected formats

#### 2. Store Tests (`tests/test_store.py`)

Test `store.py` against a temporary directory (no real EBS needed). Verify:

- `load()` returns `{}` when file is missing
- `load()` returns `{}` when file is empty
- `save()` then `load()` round-trips correctly
- `save()` is atomic — a concurrent read during write never sees partial data
- File permissions and directory creation work

#### 3. Cold Start Tests (`tests/test_cold_start.py`)

Test the bootstrap logic for each scheduled cog. Use a temp data dir and mock the Discord channel (don't actually post). Verify:

**New Market Alerts:**

- When `seen_markets.json` is missing, first run populates it with all active market IDs
- First run posts nothing to the channel
- Second run with a new market added posts only that market
- Second run with no new markets posts nothing

**Volume Movers:**

- When `volume_snapshots.json` is missing, first run takes a snapshot but generates no report
- With only one snapshot, report hour is reached but no report is posted (no comparison point)
- With two snapshots ~24h apart, report is generated with correct top movers

#### 4. State Lifecycle Tests (`tests/test_state_lifecycle.py`)

Test pruning and data hygiene. Verify:

**Seen markets pruning:**

- After a run, IDs for markets no longer in the active response are removed from `seen_ids`
- The file never grows unboundedly

**Volume snapshot pruning:**

- After a write, snapshots older than 25 hours are deleted
- With 30 hours of snapshots, only the last 25 are kept

**Mid-cycle edge cases:**

- Bot restarts mid-hour — next run picks up from existing state, no duplicate alerts
- A market appears and disappears within the same hour — never alerted, ID pruned on next cycle
- Volume snapshot taken, then bot restarts — snapshot persists, next snapshot is additive
- Clock skew / slightly irregular intervals — report logic finds the closest snapshot to 24h ago, not exact

## Configuration

All via environment variables. See `.env.example`.

| Variable                   | Required | Default                            | Description                             |
| -------------------------- | -------- | ---------------------------------- | --------------------------------------- |
| `DISCORD_BOT_TOKEN`        | Yes      | —                                  | Bot token                               |
| `DISCORD_GUILD_ID`         | No       | —                                  | Guild ID for instant slash command sync |
| `POLYMARKET_GAMMA_API_URL` | No       | `https://gamma-api.polymarket.com` | Gamma API base URL                      |
| `POLYMARKET_CLOB_API_URL`  | No       | `https://clob.polymarket.com`      | CLOB API base URL                       |
| `ALERT_CHANNEL_ID`         | Yes      | —                                  | Channel for new market alerts           |
| `VOLUME_REPORT_CHANNEL_ID` | No       | `ALERT_CHANNEL_ID`                 | Channel for daily volume report         |
| `VOLUME_REPORT_HOUR`       | No       | `9`                                | Hour (UTC) to post the volume report    |
| `OPPORTUNITY_CHANNEL_ID`   | No       | `ALERT_CHANNEL_ID`                 | Channel for opportunity alerts          |
| `OPPORTUNITY_MAX_VOLUME`   | No       | `10000`                            | Max volume to qualify as low-liquidity  |
| `OPPORTUNITY_MIN_SPREAD`   | No       | `0.05`                             | Min spread to qualify as opportunity    |
| `DATA_DIR`                 | No       | `/app/data`                        | Directory for persistent state files    |
