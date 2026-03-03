"""BackgroundTasks — run tasks after the response is sent."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("hawkapi.background")


class BackgroundTasks:
    """Collect and run background tasks after the response is sent.

    Usage:
        @app.post("/send-email")
        async def send_email(tasks: BackgroundTasks):
            tasks.add_task(send_notification, email="user@example.com")
            return {"status": "queued"}
    """

    __slots__ = ("_tasks",)

    def __init__(self) -> None:
        self._tasks: list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = []

    def add_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Add a task to be run in the background after the response."""
        self._tasks.append((func, args, kwargs))

    async def run(self) -> None:
        """Execute all queued tasks."""
        for func, args, kwargs in self._tasks:
            try:
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Background task %s failed", func.__name__)
        self._tasks.clear()
