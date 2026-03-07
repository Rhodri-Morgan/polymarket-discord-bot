"""Async JSON file I/O with atomic writes for persistent state."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

DATA_DIR: Path = Path(os.environ.get("DATA_DIR", "/app/data"))


def _path_for(name: str) -> Path:
    """Return the full path for a state file, appending .json if needed."""
    if not name.endswith(".json"):
        name = f"{name}.json"
    return DATA_DIR / name


async def load(name: str) -> dict:
    """Load a JSON state file. Returns {} if the file is missing or empty."""

    def _read() -> dict:
        path = _path_for(name)
        if not path.exists():
            return {}
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        return json.loads(text)

    return await asyncio.to_thread(_read)


async def save(name: str, data: dict) -> None:
    """Atomically write *data* as JSON. Creates DATA_DIR if needed."""

    def _write() -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = _path_for(name)
        fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, path)
        except BaseException:
            # Clean up the temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    await asyncio.to_thread(_write)
