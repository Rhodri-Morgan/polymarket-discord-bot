# Polymarket Discord Bot

![deployed.png](https://img.shields.io/badge/-Deployed-green)

A Discord bot that surfaces trending [Polymarket](https://polymarket.com) prediction market events, ranked by volume velocity.

## Quick Start (Docker)

```bash
direnv allow          # loads secrets from AWS Secrets Manager and writes .env
make docker-run
```

## Prerequisites

- [Python 3.11+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Docker](https://www.docker.com/)
- [Node.js](https://nodejs.org/) (for openlogs)
- [openlogs](https://github.com/charlietlamb/openlogs)
- [direnv](https://direnv.net/) (auto-loads secrets via `.envrc`)
- [AWS CLI](https://aws.amazon.com/cli/) and [jq](https://stedolan.github.io/jq/) (used by `.envrc` to fetch secrets)

## Quick Start (Local)

```bash
direnv allow
make install-dev
make install-git-hooks
make run
```

Git commits run `ruff` through a pre-commit hook once installed.

## Slash Commands

Commands are synced globally. `/commands` is DM-only; `/trending` and `/mispriced` run in a server channel and post results into a thread.

| Command      | Context  | Description                                           |
| ------------ | -------- | ----------------------------------------------------- |
| `/commands`  | DM only  | List the available commands                           |
| `/trending`  | Channel  | Top trending Polymarket events from the last 48 hours |
| `/mispriced` | Channel  | Find mispriced markets with arbitrage opportunities   |

## Scheduled Posts

| Feature               | Schedule         | Description                                                                                                       |
| --------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Trending Events**   | 00:00, 12:00 UTC | Posts top 100 events ranked by volume velocity to a Discord thread. Excludes sports, esports, crypto, weather.    |
| **Mispriced Markets** | 08:00 UTC        | Scans negRisk events for arbitrage opportunities where outcome YES prices deviate from 1.0. Filters by liquidity. |

## Configuration

| Variable             | Required | Default | Description                              |
| -------------------- | -------- | ------- | ---------------------------------------- |
| `DISCORD_BOT_TOKEN`  | Yes      | —       | Discord bot token                        |
| `DISCORD_CHANNEL_ID` | Yes      | —       | Channel for scheduled trending/mispriced posts |
| `HEALTH_PORT`        | No       | `4000`  | Health-check HTTP port                   |

In prod, secrets come from AWS Secrets Manager via the ECS task definition. Locally, `.envrc` pulls `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` from `local-polymarket-discord-bot` and writes a `.env` file consumed by `make docker-*`.

## Makefile Targets

| Target                   | Description                        |
| ------------------------ | ---------------------------------- |
| `make docker-run`        | Build + run the bot in Docker      |
| `make docker-dev`        | Build + run the bot                |
| `make docker-test`       | Run pytest in Docker               |
| `make docker-logs`       | Print latest docker bot/test logs  |
| `make docker-build`      | Build the Docker image             |
| `make docker-shell`      | Interactive shell in the container |
| `make install-git-hooks` | Install the git pre-commit hook    |
| `make run`               | Run the bot locally                |
| `make test`              | Run pytest locally                 |

## Project Structure

See [AGENTS.md](AGENTS.md) for architecture, patterns, and contributing conventions.
