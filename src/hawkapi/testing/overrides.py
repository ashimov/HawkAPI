"""Scoped DI overrides for testing — no global mutation."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from hawkapi.app import HawkAPI
from hawkapi.di.container import Container


@contextmanager
def override(
    app_or_container: HawkAPI | Container,
    overrides: dict[type, Callable[..., Any]],
):
    """Temporarily replace DI providers for testing.

    No global mutation — scoped to the `with` block.

    Usage:
        with override(app, {DBSession: lambda: mock_session}):
            client = TestClient(app)
            response = client.get("/users")
    """
    container = (
        app_or_container.container if isinstance(app_or_container, HawkAPI) else app_or_container
    )

    import sys

    contexts: list[Any] = []
    exc_info: tuple[Any, ...] = (None, None, None)
    try:
        for service_type, factory in overrides.items():
            ctx = container.override(service_type, factory=factory)
            ctx.__enter__()
            contexts.append(ctx)
        yield
    except BaseException:
        exc_info = sys.exc_info()
        raise
    finally:
        for ctx in reversed(contexts):
            ctx.__exit__(*exc_info)
