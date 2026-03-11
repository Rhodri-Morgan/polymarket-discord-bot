"""Bot configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    discord_bot_token: str
    discord_guild_id: int | None
    discord_channel_id: int | None
    gamma_api_url: str
    data_dir: str

    @classmethod
    def from_env(cls) -> Settings:
        """Construct settings from environment variables and default values."""
        token = os.environ["DISCORD_BOT_TOKEN"]
        guild_id_raw = os.environ.get("DISCORD_GUILD_ID", "").strip("'\"")
        channel_raw = os.environ.get("DISCORD_CHANNEL_ID", "").strip("'\"")

        return cls(
            discord_bot_token=token.strip("'\""),
            discord_guild_id=int(guild_id_raw) if guild_id_raw else None,
            discord_channel_id=int(channel_raw) if channel_raw else None,
            gamma_api_url=os.environ.get("POLYMARKET_GAMMA_API_URL", "https://gamma-api.polymarket.com"),
            data_dir=os.environ.get("DATA_DIR", "/app/data").strip("'\""),
        )


settings = Settings.from_env()
