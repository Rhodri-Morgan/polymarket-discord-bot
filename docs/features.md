# Feature Design — Scheduled Alerts & Market Discovery

## Deployment

Single EC2 instance running the Docker image. An EBS volume is mounted at `/app/data` for persistence. Deployed via Ansible.

```
EC2 instance
├── Docker: polymarket-bot
│   ├── /app/data/  →  EBS mount (persisted)
│   │   ├── seen_markets.json
│   │   └── volume_snapshots.json
│   ├── .env        →  injected at deploy
│   └── ~/.aws      →  mounted read-only
```

### Data Lifecycle

All state files live in `/app/data/`. Data is kept lean:

- **seen_markets.json** — set of market IDs already reported. Pruned on each run: IDs for markets that are no longer active get removed.
- **volume_snapshots.json** — hourly volume snapshots keyed by timestamp. Only the last 25 hours of snapshots are kept; older entries are deleted on each write.

No database. Just JSON files on the EBS volume. Simple to inspect, back up, and wipe.

---

## Architecture Overview

discord.py provides `ext.tasks` — a built-in loop decorator that runs functions on a schedule inside the bot process. No external cron needed. Each scheduled feature is its own cog with a task loop that posts to a configured Discord channel.

```
src/polymarket_bot/
├── cogs/
│   ├── polymarket.py        # Existing: interactive slash commands
│   ├── new_markets.py       # Hourly: new market alerts
│   ├── volume_movers.py     # Daily: biggest volume changes
│   └── opportunities.py     # Hourly: low-liquidity new market finder
├── store.py                 # Read/write JSON state files from /app/data
```

### Cold Start / Bootstrap

When the bot starts and a state file is empty or missing, it **bootstraps silently** — populates the file with current data without posting any alerts. This means:

- **New Market Alerts:** first run fetches all active markets, writes them all to `seen_markets.json`, posts nothing. From the second run onward, only genuinely new markets trigger alerts.
- **Volume Movers:** first run takes a full volume snapshot as the baseline. The daily report only fires once there are two snapshots at least ~24h apart. Until then, it just keeps snapshotting.

This way the bot is immediately useful after a fresh deploy or data wipe — no waiting a full cycle before alerts start working.

### Shared Pattern

Each alert cog follows the same shape:

1. A `@tasks.loop(hours=N)` decorated method that runs on schedule
2. A `cog_load` that checks for existing state — if empty, runs a silent bootstrap
3. A channel ID from config (env var) to post alerts to
4. State via `store.py` — JSON files on the EBS-backed `/app/data` directory
5. A companion slash command to trigger the alert manually (e.g. `/new-markets now`)
6. A `@task.before_loop` that calls `await self.bot.wait_until_ready()` so the loop doesn't fire before the bot is connected

### store.py

Thin helper for reading/writing JSON files to the data directory:

```python
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))

async def load(name: str) -> dict | list
async def save(name: str, data: dict | list) -> None
```

Atomic writes (write to temp file, then rename) to prevent corruption if the process is killed mid-write.

---

## Feature 1: New Market Alerts (Hourly)

**Goal:** Every hour, check for markets that didn't exist in the previous check and post them to a channel.

**How it works:**

- **Bootstrap (empty/missing state):** fetch all active markets, write every ID to `seen_markets.json`, post nothing. This seeds the baseline so only markets created _after_ startup trigger alerts.
- **Normal run:** fetch active markets, diff against seen set, post new ones as embeds with question, outcomes, volume, and link.
- **Cleanup:** update `seen_markets.json` — add new IDs, prune IDs for markets no longer active.

**API:** `GET /markets?active=true&closed=false&limit=100` (paginate if needed, sort by creation date descending)

**Config:**

- `ALERT_CHANNEL_ID` — Discord channel to post alerts to

**Slash command:** `/new-markets` — manually trigger the check

**State file:** `seen_markets.json`

```json
{
  "seen_ids": ["market-id-1", "market-id-2", ...],
  "last_check": "2026-03-07T14:00:00Z"
}
```

**Pruning:** On each run, remove IDs from `seen_ids` that are no longer in the active markets response. This keeps the file small over time.

---

## Feature 2: Volume Movers (Daily)

**Goal:** Once per day, report the markets with the biggest absolute and percentage increases in volume over the last 24 hours.

**How it works:**

- **Bootstrap (empty/missing state):** take an immediate volume snapshot as the baseline. No report is generated — just seeds `volume_snapshots.json` with the starting point. The first real report fires after ~24h of snapshots exist.
- **Hourly:** snapshot `{market_id: {"question": ..., "volume": ...}}` for all active markets, keyed by ISO timestamp.
- **At report hour (UTC):** compare the latest snapshot to the one closest to 24h ago. Rank by absolute increase (top 10) and by percentage increase (top 10). Post both as embeds to the channel.

**API:** `GET /markets?active=true&closed=false` — volume is returned per market

**Why both absolute and percentage?**

- Absolute catches the big-money markets that everyone is piling into
- Percentage catches small markets that are suddenly getting attention (often the interesting ones)

**Config:**

- `VOLUME_REPORT_CHANNEL_ID` — channel for the daily report (or reuse `ALERT_CHANNEL_ID`)
- `VOLUME_REPORT_HOUR` — hour of day in UTC to post (default: 9)

**Slash command:** `/volume-movers` — manually trigger the report

**State file:** `volume_snapshots.json`

```json
{
  "snapshots": {
    "2026-03-07T13:00:00Z": {
      "market-id-1": {"question": "Will X happen?", "volume": 150000},
      "market-id-2": {"question": "Will Y happen?", "volume": 42000}
    },
    "2026-03-07T14:00:00Z": { ... }
  }
}
```

**Pruning:** On each write, delete any snapshot entries older than 25 hours. Only ~25 snapshots exist at any time.

---

## Feature 3: Opportunity Finder — New + Low Liquidity (Hourly)

**Goal:** Identify markets that are recently created, have low liquidity (thin order books), and could be interesting opportunities to watch or provide liquidity to.

**How it works:**

- Fetch recently created active markets (sort by newest)
- For each, check the CLOB order book depth and spread
- Flag markets where:
  - Created within the last 48 hours
  - Volume is below a threshold (e.g. < $10,000)
  - Spread is wide (e.g. > 5 cents) — indicates thin liquidity
  - Has meaningful question/topic (filter out test markets)
- Post a digest of "opportunities" with spread, volume, and midpoint price
- No state file needed — this is a stateless scan each time

**APIs:**

- `GET /markets?active=true&closed=false&order=startDate&ascending=false` (Gamma)
- `GET /spread?token_id=` (CLOB)
- `GET /book?token_id=` (CLOB)

**Config:**

- `OPPORTUNITY_CHANNEL_ID`
- `OPPORTUNITY_MAX_VOLUME` — volume threshold (default: 10000)
- `OPPORTUNITY_MIN_SPREAD` — minimum spread to flag (default: 0.05)

**Slash command:** `/opportunities` — manually trigger the scan

---

## Implementation Order

1. **New Market Alerts** — simplest, proves the scheduled-task + store pattern
2. **Volume Movers** — adds hourly snapshotting and the pruning lifecycle
3. **Opportunity Finder** — adds CLOB API integration (spread/book queries)

Each feature: write tests first (TDD), implement, run in Docker, verify in Discord.
