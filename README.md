# Polymarket Discord Bot

A Discord bot that surfaces live [Polymarket](https://polymarket.com) prediction-market data via slash commands.

## Quick Start (Local)

```bash
cp .env.example .env   # add your DISCORD_BOT_TOKEN
make install-dev
make run
```

## Quick Start (Docker)

```bash
cp .env.example .env   # add your DISCORD_BOT_TOKEN
make docker-run
```

## Slash Commands

| Command          | Description                                         |
| ---------------- | --------------------------------------------------- |
| `/markets [tag]` | List active markets, optionally filtered by tag     |
| `/new-markets`   | Manually check for newly listed markets             |
| `/volume-movers` | Show the biggest volume movers in the last 24 hours |
| `/opportunities` | Scan for low-liquidity new market opportunities     |
| `/ping`          | Check bot latency                                   |

## Scheduled Features

These run automatically in the background via `discord.ext.tasks` loops.

| Feature               | Frequency | Channel Config             | Description                                                                                  |
| --------------------- | --------- | -------------------------- | -------------------------------------------------------------------------------------------- |
| **New Market Alerts** | Hourly    | `ALERT_CHANNEL_ID`         | Detects newly listed markets and posts them. Cold start seeds state silently on first run.   |
| **Volume Snapshots**  | Hourly    | `VOLUME_REPORT_CHANNEL_ID` | Captures market volumes every hour. At the configured UTC hour, posts a daily top-10 report. |
| **Opportunity Scan**  | Hourly    | `OPPORTUNITY_CHANNEL_ID`   | Finds new markets (<48h old) with low volume and wide bid/ask spreads.                       |

## Configuration

| Variable                   | Required | Description                                                    |
| -------------------------- | -------- | -------------------------------------------------------------- |
| `DISCORD_BOT_TOKEN`        | Yes      | Your Discord bot token                                         |
| `DISCORD_GUILD_ID`         | No       | Guild ID for instant slash-command sync (dev)                  |
| `POLYMARKET_GAMMA_API_URL` | No       | Defaults to `https://gamma-api.polymarket.com`                 |
| `POLYMARKET_CLOB_API_URL`  | No       | Defaults to `https://clob.polymarket.com`                      |
| `ALERT_CHANNEL_ID`         | No       | Discord channel for new market alerts                          |
| `VOLUME_REPORT_CHANNEL_ID` | No       | Discord channel for daily volume mover reports                 |
| `VOLUME_REPORT_HOUR`       | No       | UTC hour (0–23) to post the daily report (default: 9)          |
| `OPPORTUNITY_CHANNEL_ID`   | No       | Discord channel for opportunity alerts                         |
| `OPPORTUNITY_MAX_VOLUME`   | No       | Max volume threshold for opportunities (default: 50000)        |
| `OPPORTUNITY_MIN_SPREAD`   | No       | Min bid/ask spread threshold for opportunities (default: 0.05) |
| `DATA_DIR`                 | No       | State file directory (default: `/app/data`)                    |

## Project Structure

See [AGENTS.md](AGENTS.md) for full architecture docs and contributing conventions.
