"""Entry point: python -m polymarket_bot"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from polymarket_bot.bot import PolymarketBot
from polymarket_bot.config import settings


async def main() -> None:
    async with PolymarketBot() as bot:
        await bot.start(settings.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
