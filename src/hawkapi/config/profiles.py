"""Environment profiles (dev/staging/production)."""

from __future__ import annotations

import os
from pathlib import Path

from hawkapi.config.env import load_dotenv


def load_profile_env(
    profile: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, str]:
    """Load environment variables with profile layering.

    Loading order (later overrides earlier):
    1. .env (base defaults)
    2. .env.{profile} (profile-specific overrides)
    3. Actual environment variables (always win)
    """
    base_dir = Path(base_dir) if base_dir else Path.cwd()
    profile = profile or os.environ.get("HAWK_ENV", "development")

    result: dict[str, str] = {}

    # Layer 1: base .env
    base_env = load_dotenv(base_dir / ".env")
    result.update(base_env)

    # Layer 2: profile-specific .env
    profile_env = load_dotenv(base_dir / f".env.{profile}")
    result.update(profile_env)

    # Layer 3: actual environment variables override everything
    for key in result:
        env_val = os.environ.get(key)
        if env_val is not None:
            result[key] = env_val

    return result
