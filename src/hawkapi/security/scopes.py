"""OAuth2-style scope carriers for DI-level security dependencies.

``Security`` is a ``Depends`` subclass that additionally carries a list of
required scopes. Routes aggregate every ``Security().scopes`` declared in
their ``dependencies=[...]`` list (and in the handler signature) into a
single per-route ``required_scopes`` tuple.

``SecurityScopes`` is the framework-injected context object — any callable
whose signature declares a ``SecurityScopes``-annotated parameter receives
the route's required scopes at resolution time. The user inspects the list
and decides whether to raise ``HTTPException(403)`` — matching FastAPI,
the framework does not auto-enforce.

OpenAPI reflection lives in ``src/hawkapi/openapi/schema.py`` and attaches
the route's required scopes to the first detected security scheme.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from hawkapi.di.depends import Depends


class Security(Depends):
    """``Depends`` subclass that also declares required OAuth2 scopes.

    Usage::

        @app.get(
            "/items",
            dependencies=[Security(current_user, scopes=["read:items"])],
        )
        async def list_items(): ...

    ``scopes`` is stored as a list on the instance; the route merges every
    ``Security().scopes`` into a deduplicated, sorted tuple at registration
    time.
    """

    __slots__ = ("scopes",)

    def __init__(
        self,
        dependency: Any = None,
        *,
        scopes: Sequence[str] | None = None,
    ) -> None:
        super().__init__(dependency=dependency)
        self.scopes: list[str] = list(scopes) if scopes else []


@dataclass(frozen=True, slots=True)
class SecurityScopes:
    """Framework-injected container of the current route's required scopes.

    A callable receives this by declaring a parameter annotated
    ``SecurityScopes``. The callable then decides how to validate the
    request's scopes against ``scopes``. ``scope_str`` is the RFC 6749
    space-separated representation used in ``WWW-Authenticate`` headers.
    """

    scopes: tuple[str, ...] = ()

    @property
    def scope_str(self) -> str:
        return " ".join(self.scopes)


__all__ = ["Security", "SecurityScopes"]
