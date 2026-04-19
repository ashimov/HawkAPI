"""Feature-flags subsystem for HawkAPI."""

from __future__ import annotations

from hawkapi.flags._decorator import requires_flag
from hawkapi.flags._di import get_flags
from hawkapi.flags.base import EvalContext, FlagDisabled, FlagProvider, Flags
from hawkapi.flags.providers import EnvFlagProvider, FileFlagProvider, StaticFlagProvider

__all__ = [
    "EvalContext",
    "EnvFlagProvider",
    "FileFlagProvider",
    "FlagDisabled",
    "FlagProvider",
    "Flags",
    "StaticFlagProvider",
    "get_flags",
    "requires_flag",
]
