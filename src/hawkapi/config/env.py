"""Environment variable and .env file loader."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path | None = None) -> dict[str, str]:
    """Load variables from a .env file into a dict (does NOT modify os.environ)."""
    path = Path.cwd() / ".env" if path is None else Path(path)

    if not path.is_file():
        return {}

    result: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            result[key] = value
    return result


def get_env(key: str, default: str | None = None) -> str | None:
    """Get an environment variable."""
    return os.environ.get(key, default)
