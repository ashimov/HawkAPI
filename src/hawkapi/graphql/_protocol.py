"""GraphQLExecutor Protocol — the interface executors must implement."""

from __future__ import annotations

from typing import Any, Protocol


class GraphQLExecutor(Protocol):
    """Protocol for GraphQL executor callables.

    Users implement this or use one of the built-in adapters in
    ``hawkapi.graphql.adapters``.
    """

    async def __call__(
        self,
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a GraphQL operation and return the response dict.

        The returned dict is JSON-encoded as-is and should contain
        ``"data"`` and/or ``"errors"`` keys per the GraphQL spec.
        """
        ...


__all__ = ["GraphQLExecutor"]
