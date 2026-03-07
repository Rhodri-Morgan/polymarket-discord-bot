"""Bot configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    discord_guild_id: int | None
    gamma_api_url: str
    clob_api_url: str
    alert_channel_id: int | None
    volume_report_channel_id: int | None
    volume_report_hour: int
    opportunity_channel_id: int | None
    opportunity_max_volume: float
    opportunity_min_spread: float
    data_dir: str

    @classmethod
    def from_env(cls) -> Settings:
        token = os.environ["DISCORD_BOT_TOKEN"]
        guild_id_raw = os.environ.get("DISCORD_GUILD_ID", "").strip("'\"")
        alert_raw = os.environ.get("ALERT_CHANNEL_ID", "").strip("'\"")
        alert_channel_id = int(alert_raw) if alert_raw else None

        vol_report_raw = os.environ.get("VOLUME_REPORT_CHANNEL_ID", "").strip("'\"")
        volume_report_channel_id = int(vol_report_raw) if vol_report_raw else alert_channel_id

        opp_raw = os.environ.get("OPPORTUNITY_CHANNEL_ID", "").strip("'\"")
        opportunity_channel_id = int(opp_raw) if opp_raw else alert_channel_id

        return cls(
            discord_bot_token=token.strip("'\""),
            discord_guild_id=int(guild_id_raw) if guild_id_raw else None,
            gamma_api_url=os.environ.get("POLYMARKET_GAMMA_API_URL", "https://gamma-api.polymarket.com"),
            clob_api_url=os.environ.get("POLYMARKET_CLOB_API_URL", "https://clob.polymarket.com"),
            alert_channel_id=alert_channel_id,
            volume_report_channel_id=volume_report_channel_id,
            volume_report_hour=int(os.environ.get("VOLUME_REPORT_HOUR", "9").strip("'\"")),
            opportunity_channel_id=opportunity_channel_id,
            opportunity_max_volume=float(os.environ.get("OPPORTUNITY_MAX_VOLUME", "10000").strip("'\"")),
            opportunity_min_spread=float(os.environ.get("OPPORTUNITY_MIN_SPREAD", "0.05").strip("'\"")),
            data_dir=os.environ.get("DATA_DIR", "/app/data").strip("'\""),
        )


settings = Settings.from_env()
