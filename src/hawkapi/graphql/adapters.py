"""Optional adapters for popular GraphQL libraries.

Both functions use lazy imports so graphql-core and strawberry are
NOT required at install time and are NOT imported at module load time.
"""

from __future__ import annotations

from typing import Any, cast

from hawkapi.graphql._protocol import GraphQLExecutor


def from_graphql_core(schema: Any, *, middleware: Any = None) -> GraphQLExecutor:
    """Create a :class:`GraphQLExecutor` backed by ``graphql-core``.

    ``graphql-core`` is only imported when the returned executor is called,
    so the package is not required unless this adapter is actually used.

    Args:
        schema: A ``graphql.GraphQLSchema`` instance.
        middleware: Optional graphql-core middleware list.

    Returns:
        An async callable implementing :class:`GraphQLExecutor`.
    """

    async def executor(
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        import graphql as _gql  # noqa: PLC0415  # pyright: ignore[reportMissingImports]

        _result: Any = cast(
            Any,
            await _gql.graphql(  # pyright: ignore[reportUnknownMemberType]
                schema,
                query,
                variable_values=variables,
                operation_name=operation_name,
                context_value=context,
                middleware=middleware,
            ),
        )
        response: dict[str, Any] = {}
        if _result.data is not None:
            response["data"] = _result.data
        if _result.errors:
            response["errors"] = [
                {"message": str(e), "path": getattr(e, "path", None)} for e in _result.errors
            ]
        return response

    return executor  # type: ignore[return-value]


def from_strawberry(schema: Any, *, root_value: Any = None) -> GraphQLExecutor:
    """Create a :class:`GraphQLExecutor` backed by ``strawberry-graphql``.

    ``strawberry`` is only imported when the returned executor is called.

    Args:
        schema: A ``strawberry.Schema`` instance.
        root_value: Optional root value passed to the schema executor.

    Returns:
        An async callable implementing :class:`GraphQLExecutor`.
    """

    async def executor(
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        import strawberry  # noqa: PLC0415, F401  # pyright: ignore[reportMissingImports,reportUnusedImport]

        _result: Any = await schema.execute(
            query,
            variable_values=variables,
            operation_name=operation_name,
            context_value=context,
            root_value=root_value,
        )
        response: dict[str, Any] = {}
        if _result.data is not None:
            response["data"] = _result.data
        if _result.errors:
            response["errors"] = [
                {"message": str(e), "path": getattr(e, "path", None)} for e in _result.errors
            ]
        return response

    return executor  # type: ignore[return-value]


__all__ = ["from_graphql_core", "from_strawberry"]
