"""Bot configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

GAMMA_API_URL = "https://gamma-api.polymarket.com"


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    discord_bot_token: str
    discord_channel_id: int

    @classmethod
    def from_env(cls) -> Settings:
        """Construct settings from environment variables and default values."""
        token = os.environ["DISCORD_BOT_TOKEN"]
        channel_id = os.environ["DISCORD_CHANNEL_ID"].strip("'\"")

        return cls(
            discord_bot_token=token.strip("'\""),
            discord_channel_id=int(channel_id),
        )


settings = Settings.from_env()
