"""Seed local dev data so scheduled features produce output immediately.

Creates state files that simulate 24 hours of prior data:
- seen_markets.json: all markets EXCEPT the 5 most recent (so they appear as "new")
- volume_snapshots.json: a snapshot from ~24h ago with lower volumes (simulating growth)

Usage:
    python scripts/seed_dev_data.py [--data-dir ./data]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

GAMMA_API_URL = "https://gamma-api.polymarket.com"


def fetch_active_markets(limit: int = 200) -> list[dict]:
    """Fetch active markets from the Gamma API."""
    all_markets = []
    offset = 0
    page_size = 100
    while len(all_markets) < limit:
        resp = requests.get(
            f"{GAMMA_API_URL}/markets",
            params={
                "active": "true",
                "closed": "false",
                "limit": page_size,
                "offset": offset,
            },
        )
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        all_markets.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return all_markets[:limit]


def seed_seen_markets(markets: list[dict], data_dir: Path, num_unseen: int = 5) -> None:
    """Save seen_markets.json with the oldest markets, leaving the newest as 'unseen'."""
    all_ids = [m["id"] for m in markets]

    # Leave the last N markets out so they appear as "new" on first run
    seen_ids = all_ids[:-num_unseen] if len(all_ids) > num_unseen else []

    state = {
        "seen_ids": seen_ids,
        "last_check": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }

    path = data_dir / "seen_markets.json"
    path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"  seen_markets.json: {len(seen_ids)} seen, {len(all_ids) - len(seen_ids)} will appear as new")


def seed_volume_snapshots(markets: list[dict], data_dir: Path) -> None:
    """Save volume_snapshots.json with a 24h-ago snapshot at ~80% of current volumes."""
    now = datetime.now(timezone.utc)
    ts_24h_ago = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_now = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    old_snapshot = {}
    new_snapshot = {}

    for m in markets:
        market_id = m.get("id")
        if not market_id:
            continue
        question = m.get("question", "")
        try:
            volume = float(m.get("volume", 0))
        except (TypeError, ValueError):
            volume = 0.0

        new_snapshot[market_id] = {"question": question, "volume": volume}
        # Simulate 24h ago: volumes were ~70-90% of current (randomised per market)
        import hashlib

        hash_val = int(hashlib.md5(market_id.encode()).hexdigest()[:8], 16)
        ratio = 0.7 + (hash_val % 20) / 100  # 0.70 to 0.89
        old_snapshot[market_id] = {"question": question, "volume": round(volume * ratio, 2)}

    state = {
        "snapshots": {
            ts_24h_ago: old_snapshot,
            ts_now: new_snapshot,
        }
    }

    path = data_dir / "volume_snapshots.json"
    path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"  volume_snapshots.json: {len(new_snapshot)} markets, 2 snapshots (now + 24h ago)")


def main():
    parser = argparse.ArgumentParser(description="Seed dev data for local testing")
    parser.add_argument("--data-dir", default="./data", help="Data directory (default: ./data)")
    parser.add_argument("--num-unseen", type=int, default=5, help="Number of markets to leave as 'new' (default: 5)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching active markets from {GAMMA_API_URL}...")
    markets = fetch_active_markets()
    print(f"  Got {len(markets)} markets")

    print("Seeding state files...")
    seed_seen_markets(markets, data_dir, num_unseen=args.num_unseen)
    seed_volume_snapshots(markets, data_dir)

    print(f"\nDone. Files written to {data_dir}/")
    print("Start the bot with DATA_DIR pointed here:")
    print(f"  DATA_DIR={data_dir} make run")


if __name__ == "__main__":
    main()
