# Cog Lifecycle

Every feature is a `commands.Cog` under `src/polymarket_bot/cogs/`. The bot auto-discovers and loads any `.py` file in that directory (excluding `_`-prefixed files).

## Standard Cog Skeleton

```python
"""Feature Name cog — one-line description."""

from __future__ import annotations

import logging
from datetime import time, timezone
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from polymarket_bot.bot import PolymarketBot

log = logging.getLogger(__name__)


class FeatureCog(commands.Cog, name="Feature"):
    """One-line description of this cog."""

    def __init__(self, bot: PolymarketBot) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        """Create HTTP session and start scheduled tasks."""
        from polymarket_bot.config import GAMMA_API_URL

        self.gamma_url = GAMMA_API_URL
        self.channel_id = settings.discord_channel_id
        self.session = aiohttp.ClientSession()
        self.check_loop.start()

    async def cog_unload(self) -> None:
        """Stop tasks and close HTTP session."""
        self.check_loop.cancel()
        if self.session:
            await self.session.close()

    @tasks.loop(time=[time(hour=0, tzinfo=timezone.utc)])
    async def check_loop(self) -> None:
        await self._run_check()

    @check_loop.before_loop
    async def before_check_loop(self) -> None:
        await self.bot.wait_until_ready()

    async def _run_check(self) -> None:
        """Scheduled task body — fetch data and post to channel."""
        ...

    @app_commands.command(name="feature", description="...")
    async def feature_cmd(self, interaction: discord.Interaction) -> None:
        """Slash command handler."""
        ...


async def setup(bot: PolymarketBot) -> None:
    await bot.add_cog(FeatureCog(bot))
```

## Lifecycle Hooks

| Hook            | When                              | Use for                                      |
| --------------- | --------------------------------- | -------------------------------------------- |
| `__init__`      | Bot loads the cog class           | Store bot ref, declare attributes (no I/O)   |
| `cog_load`      | After `add_cog()`, before ready   | Create `aiohttp.ClientSession`, start loops  |
| `cog_unload`    | When cog is removed or bot shuts down | Cancel loops, close sessions              |
| `before_loop`   | Before first loop iteration       | `await self.bot.wait_until_ready()`          |

## Session Management

Each cog owns its own `aiohttp.ClientSession`. Sessions are:
- Created in `cog_load` (not `__init__`, which must be sync and should not do I/O)
- Closed in `cog_unload`
- Checked for `None` before use in `_run_check` and command handlers

## Scheduled Tasks

Use `discord.ext.tasks.loop` with `time=` for fixed UTC schedules (not `hours=` or `minutes=` for intervals).

Specific schedules are defined in each cog's `@tasks.loop(time=...)` decorator — see AGENTS.md or the cog source for current values.

## Slash Commands

All commands use `app_commands.command` (not prefix commands). The standard pattern:

1. `interaction.response.defer()` — must respond within 3 seconds
2. Fetch data
3. Handle empty results with `interaction.followup.send()`
4. For thread-based output, use `interaction.channel` (see `docs/1_thread_output_pattern.md`)

## Auto-Discovery

`bot.py` loads cogs by globbing `src/polymarket_bot/cogs/*.py` and skipping `_`-prefixed files. No registration step needed — just create the file with a `setup()` function.
