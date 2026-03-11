"""Entry point: python -m polymarket_bot"""

import asyncio
import logging

from polymarket_bot.bot import PolymarketBot
from polymarket_bot.config import settings
from polymarket_bot.health import start_health_server


async def main() -> None:
    """Start the health server and run the Discord bot until shutdown."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    health_runner = await start_health_server()
    try:
        async with PolymarketBot() as bot:
            await bot.start(settings.discord_bot_token)
    finally:
        await health_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
