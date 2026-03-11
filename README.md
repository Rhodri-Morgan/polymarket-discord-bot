# Polymarket Discord Bot

A Discord bot that surfaces trending [Polymarket](https://polymarket.com) prediction market events, ranked by volume velocity.

## Quick Start (Docker)

```bash
cp .env.example .env   # fill in values
make docker-run
```

## Quick Start (Local)

```bash
cp .env.example .env   # fill in values
make install-dev
make install-git-hooks
make run
```

Git commits run `ruff` through a pre-commit hook once installed.

## Slash Commands

| Command      | Description                                           |
| ------------ | ----------------------------------------------------- |
| `/trending`  | Top trending Polymarket events from the last 48 hours |
| `/mispriced` | Find mispriced markets with arbitrage opportunities   |

## Scheduled Posts

| Feature               | Schedule         | Description                                                                                                       |
| --------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Trending Events**   | 00:00, 12:00 UTC | Posts top 100 events ranked by volume velocity to a Discord thread. Excludes sports, esports, crypto, weather.    |
| **Mispriced Markets** | 08:00 UTC        | Scans negRisk events for arbitrage opportunities where outcome YES prices deviate from 1.0. Filters by liquidity. |

## Configuration

| Variable                   | Required | Default                            | Description                             |
| -------------------------- | -------- | ---------------------------------- | --------------------------------------- |
| `DISCORD_BOT_TOKEN`        | Yes      | —                                  | Discord bot token                       |
| `DISCORD_GUILD_ID`         | No       | —                                  | Guild ID for instant slash command sync |
| `DISCORD_CHANNEL_ID`       | No       | —                                  | Channel for scheduled posts             |
| `POLYMARKET_GAMMA_API_URL` | No       | `https://gamma-api.polymarket.com` | Gamma API base URL                      |
| `DATA_DIR`                 | No       | `/app/data`                        | Directory for persistent data files     |

## Makefile Targets

| Target              | Description                        |
| ------------------- | ---------------------------------- |
| `make docker-run`   | Build + run the bot in Docker      |
| `make docker-dev`   | Seed data + run the bot            |
| `make docker-test`  | Run pytest in Docker               |
| `make docker-build` | Build the Docker image             |
| `make docker-shell` | Interactive shell in the container |
| `make install-git-hooks` | Install the git pre-commit hook |
| `make run`          | Run the bot locally                |
| `make test`         | Run pytest locally                 |

## Project Structure

See [AGENTS.md](AGENTS.md) for architecture, patterns, and contributing conventions.
