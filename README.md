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

## Commands

| Command             | Description                                     |
| ------------------- | ----------------------------------------------- |
| `/markets [tag]`    | List active markets, optionally filtered by tag |
| `/search <query>`   | Search markets by keyword                       |
| `/market <slug>`    | Get market details with live prices             |
| `/price <token_id>` | Get live price and bid/ask spread for a token   |
| `/book <token_id>`  | Get the order book for a token                  |
| `/ping`             | Check bot latency                               |

## Configuration

| Variable                   | Required | Description                                    |
| -------------------------- | -------- | ---------------------------------------------- |
| `DISCORD_BOT_TOKEN`        | Yes      | Your Discord bot token                         |
| `DISCORD_GUILD_ID`         | No       | Guild ID for instant slash-command sync (dev)  |
| `POLYMARKET_GAMMA_API_URL` | No       | Defaults to `https://gamma-api.polymarket.com` |
| `POLYMARKET_CLOB_API_URL`  | No       | Defaults to `https://clob.polymarket.com`      |

## Project Structure

See [AGENTS.md](AGENTS.md) for full architecture docs and contributing conventions.
