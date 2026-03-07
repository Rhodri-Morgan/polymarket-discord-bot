# Polymarket Discord Bot — Agent Instructions

## Project Overview

A Discord bot that surfaces live Polymarket prediction-market data via slash commands and scheduled alerts. Built with Python 3.11+ and discord.py v2.

For full system design, deployment model, cold start behaviour, persistence, and test strategy, see **[ARCHITECTURE.md](ARCHITECTURE.md)**.

For planned features and implementation details, see **[docs/features.md](docs/features.md)**.

## Key Patterns

- **Docker-first**: all development and testing should be done through Docker. Use `make docker-*` targets for building, running, testing, and seeding data. Local targets exist as a fallback but Docker is the preferred workflow.
- **Cog-based**: each feature area is a `commands.Cog` under `src/polymarket_bot/cogs/`. The bot auto-discovers and loads any `.py` file in that directory (excluding `_`-prefixed files).
- **Slash commands only**: all user-facing commands use `app_commands` (not prefix commands). The `!` prefix is configured but reserved for admin/debug use.
- **Async HTTP**: each cog manages its own `aiohttp.ClientSession` via `cog_load` / `cog_unload`.
- **Scheduled tasks**: `discord.ext.tasks` loops for background alerts. See ARCHITECTURE.md for the shared cog pattern.
- **Cold start bootstrap**: scheduled cogs silently seed state files on first run — no empty cycle. See ARCHITECTURE.md § Cold Start.
- **JSON persistence**: state files on EBS-backed `/app/data`. Atomic writes, self-pruning. See ARCHITECTURE.md § Persistence Layer.
- **Config**: all secrets and tunables come from environment variables (see `.env.example`). Never hardcode tokens or URLs.

## Development

### Setup

```bash
cp .env.example .env   # fill in real values
make docker-dev        # seed data + run the bot in Docker
```

### Makefile Targets — Docker (preferred)

All Docker targets mount `.env`, `~/.aws` (read-only, `AWS_PROFILE=rtm`), and `./data:/app/data`.

| Target              | Description                                    |
| ------------------- | ---------------------------------------------- |
| `make docker-build` | Build the Docker image                         |
| `make docker-run`   | Build + run the bot in Docker                  |
| `make docker-seed`  | Build + seed dev data (backdated state files)  |
| `make docker-dev`   | Seed data then run the bot (full dev workflow) |
| `make docker-test`  | Run pytest in Docker                           |
| `make docker-shell` | Interactive bash shell in the container        |
| `make docker-clean` | Remove the Docker image                        |

### Makefile Targets — Local (fallback)

| Target             | Description                    |
| ------------------ | ------------------------------ |
| `make install`     | Install production deps via uv |
| `make install-dev` | Install dev deps via uv        |
| `make run`         | Run the bot locally            |
| `make seed`        | Seed dev data locally          |
| `make dev`         | Seed data + run the bot        |
| `make test`        | Run pytest locally             |
| `make clean`       | Remove .venv, caches, and data |

### Adding a New Cog

1. Create `src/polymarket_bot/cogs/your_feature.py`
2. Define a class extending `commands.Cog`
3. Add an `async def setup(bot)` function at module level
4. The bot will auto-load it on next restart

### Test-Driven Development

This project follows **strict TDD**. For every new feature:

1. **Write tests first** — before implementing any feature or API integration, write failing tests that define the expected behaviour.
2. **Verify the tests fail** — run `make test` to confirm they fail for the right reason.
3. **Implement the feature** — write the minimum code to make the tests pass.
4. **Run tests again** — confirm everything passes before moving on.

**This is mandatory.** Do not implement features without writing tests first. Do not skip edge cases.

**Mock data must match real API responses.** All tests involving the Polymarket API or any other external API must inspect the real API structure (via curl or official documentation) to ensure mocked data and assertions accurately reflect the API's actual response format and data types. This prevents drift between mocks and real API responses. For example, the Gamma API returns `volume` as a string, `clobTokenIds` as a JSON-encoded string, and `outcomes` as a JSON-encoded string — mocks must replicate this.

Tests live in `tests/` and mirror the source structure. See ARCHITECTURE.md § Test Strategy for the full breakdown of test categories:

- **API integration tests** — real HTTP calls to Polymarket APIs, verify data shapes
- **Store tests** — JSON I/O, atomic writes, missing/empty file handling
- **Cold start tests** — bootstrap logic, silent first run, correct behaviour from second run
- **State lifecycle tests** — pruning, mid-cycle restarts, edge cases (markets appearing/disappearing within a cycle, clock skew, duplicate prevention)
