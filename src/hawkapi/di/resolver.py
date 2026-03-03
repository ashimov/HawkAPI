"""Handler dependency resolution.

Inspects handler signatures and resolves dependencies from the DI container.
"""

from __future__ import annotations

import inspect
from typing import Any, get_args, get_origin, get_type_hints

from hawkapi.di.container import Container
from hawkapi.di.depends import Depends
from hawkapi.di.scope import Scope
from hawkapi.requests.request import Request
from hawkapi.validation.constraints import Body, Cookie, Header, ParamMarker, Path, Query


def _get_annotation_marker(annotation: Any) -> ParamMarker | Depends | None:
    """Extract a marker (Path/Query/Header/Depends/etc.) from Annotated type."""
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        for arg in args[1:]:
            if isinstance(arg, (ParamMarker, Depends)):
                return arg
    return None


def _get_base_type(annotation: Any) -> type:
    """Get the base type from an annotation, stripping Annotated metadata."""
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        if args:
            first = args[0]
            if isinstance(first, type):
                for arg in args[1:]:
                    if isinstance(arg, (ParamMarker, Depends)):
                        return first
            return annotation
    if isinstance(annotation, type):
        return annotation
    return annotation


async def _resolve_callable_dep(
    dep: Any,
    request: Request,
    cleanup_stack: list[Any],
) -> Any:
    """Resolve a single callable dependency, recursively resolving sub-deps."""
    target = dep.__call__ if callable(dep) and not inspect.isfunction(dep) else dep
    try:
        dep_hints = get_type_hints(target, include_extras=True)
    except Exception:
        dep_hints = getattr(target, "__annotations__", {})
    dep_sig = inspect.signature(target)
    dep_kwargs: dict[str, Any] = {}

    for dep_name, dep_param in dep_sig.parameters.items():
        if dep_name == "self":
            continue
        if dep_name == "request":
            dep_kwargs["request"] = request
            continue

        # Check for Depends in Annotated metadata
        dep_annotation = dep_hints.get(dep_name, dep_param.annotation)
        sub_marker = _get_annotation_marker(dep_annotation)
        if isinstance(sub_marker, Depends) and sub_marker.dependency is not None:
            dep_kwargs[dep_name] = await _resolve_callable_dep(
                sub_marker.dependency, request, cleanup_stack
            )
            continue

        # Check for Depends as default value
        if isinstance(dep_param.default, Depends) and dep_param.default.dependency is not None:
            dep_kwargs[dep_name] = await _resolve_callable_dep(
                dep_param.default.dependency, request, cleanup_stack
            )
            continue

        # Use regular default if available
        if dep_param.default is not inspect.Parameter.empty:
            dep_kwargs[dep_name] = dep_param.default

    result = dep(**dep_kwargs)
    if inspect.isasyncgen(result):
        value = await result.__anext__()
        cleanup_stack.append(result)
        return value
    if inspect.isgenerator(result):
        value = next(result)
        cleanup_stack.append(result)
        return value
    if inspect.isawaitable(result):
        return await result
    return result


async def resolve_dependencies(
    handler: Any,
    request: Request,
    scope: Scope | None,
    container: Container | None,
) -> tuple[dict[str, Any], list[Any]]:
    """Resolve all dependencies for a handler from request + DI container.

    Returns (kwargs, cleanup_stack) where cleanup_stack contains generators
    that need to be finalized after the handler completes.
    """

    sig = inspect.signature(handler)
    hints = get_type_hints(handler, include_extras=True)
    kwargs: dict[str, Any] = {}
    cleanup_stack: list[Any] = []

    for name, param in sig.parameters.items():
        annotation = hints.get(name, param.annotation)
        marker = _get_annotation_marker(annotation)
        base_type = _get_base_type(annotation)

        if isinstance(marker, Path):
            value = request.path_params.get(marker.alias or name)
            if value is None and marker.has_default():
                value = marker.get_default()
            kwargs[name] = value

        elif isinstance(marker, Query):
            value = request.query_params.get(marker.alias or name)
            if value is None:
                if marker.has_default():
                    value = marker.get_default()
                elif param.default is not inspect.Parameter.empty:
                    value = param.default
            else:
                value = _coerce_value(value, base_type)
            kwargs[name] = value

        elif isinstance(marker, Header):
            header_name = (marker.alias or name).lower().replace("_", "-")
            value = request.headers.get(header_name)
            if value is None:
                if marker.has_default():
                    value = marker.get_default()
                elif param.default is not inspect.Parameter.empty:
                    value = param.default
            kwargs[name] = value

        elif isinstance(marker, Cookie):
            value = request.cookies.get(marker.alias or name)
            if value is None:
                if marker.has_default():
                    value = marker.get_default()
                elif param.default is not inspect.Parameter.empty:
                    value = param.default
            kwargs[name] = value

        elif isinstance(marker, Depends):
            # Resolve from DI container
            if marker.dependency is not None:
                kwargs[name] = await _resolve_callable_dep(
                    marker.dependency, request, cleanup_stack
                )
            else:
                resolved = False
                try:
                    if scope is not None:
                        kwargs[name] = await scope.resolve(base_type, marker.name)
                        resolved = True
                    elif container is not None and container.has(base_type, marker.name):
                        kwargs[name] = await container.resolve(base_type, marker.name)
                        resolved = True
                except LookupError:
                    pass
                if not resolved:
                    if param.default is not inspect.Parameter.empty:
                        kwargs[name] = param.default
                    else:
                        raise LookupError(f"Cannot resolve dependency {name}: {base_type.__name__}")

        elif isinstance(marker, Body) or _is_body_type(base_type):
            from hawkapi._compat.pydantic_adapter import decode_pydantic, is_pydantic_model
            from hawkapi.validation.decoder import decode_bytes
            from hawkapi.validation.errors import RequestValidationError, ValidationErrorDetail

            body_bytes = await request.body()
            if body_bytes:
                if is_pydantic_model(base_type):
                    kwargs[name] = decode_pydantic(base_type, body_bytes)
                else:
                    kwargs[name] = decode_bytes(body_bytes, base_type)
            elif param.default is not inspect.Parameter.empty:
                kwargs[name] = param.default
            else:
                raise RequestValidationError(
                    [ValidationErrorDetail(field="body", message="Request body is required")]
                )

        elif name == "request":
            kwargs[name] = request

        elif _is_background_tasks(base_type):
            from hawkapi.background import BackgroundTasks

            kwargs[name] = BackgroundTasks()

        elif name in request.path_params:
            kwargs[name] = request.path_params[name]

        elif container is not None and container.has(base_type):
            # Auto-resolve from container by type
            if scope is not None:
                kwargs[name] = await scope.resolve(base_type)
            else:
                kwargs[name] = await container.resolve(base_type)

        elif param.default is not inspect.Parameter.empty:
            qval = request.query_params.get(name)
            if qval is not None:
                kwargs[name] = _coerce_value(qval, base_type)
            else:
                kwargs[name] = param.default

        else:
            qval = request.query_params.get(name)
            if qval is not None:
                kwargs[name] = _coerce_value(qval, base_type)

    return kwargs, cleanup_stack


def _is_background_tasks(tp: type) -> bool:
    """Check if the type is BackgroundTasks."""
    from hawkapi.background import BackgroundTasks

    return isinstance(tp, type) and issubclass(tp, BackgroundTasks)  # pyright: ignore[reportUnnecessaryIsInstance]


def _is_body_type(tp: type) -> bool:
    """Check if a type should be extracted from the request body."""
    import msgspec

    from hawkapi._compat.pydantic_adapter import is_pydantic_model

    try:
        if isinstance(tp, type) and issubclass(tp, (msgspec.Struct, dict, list)):  # pyright: ignore[reportUnnecessaryIsInstance]
            return True
        return is_pydantic_model(tp)
    except TypeError:
        return False


def _unwrap_optional(tp: Any) -> type:
    """Unwrap Optional[T] / T | None to T."""
    origin = get_origin(tp)
    if origin is not None:
        import types

        if origin in (types.UnionType,) or str(origin) == "typing.Union":
            args = get_args(tp)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return non_none[0]
    return tp


def _coerce_value(value: str, target_type: type) -> Any:
    """Coerce a string value to the target type.

    Raises RequestValidationError on invalid input instead of crashing.
    """
    from hawkapi.validation.errors import RequestValidationError, ValidationErrorDetail

    target_type = _unwrap_optional(target_type)
    if target_type is bool:
        return value.lower() in ("true", "1", "yes")
    if target_type is int:
        try:
            return int(value)
        except (ValueError, TypeError) as exc:
            raise RequestValidationError(
                [
                    ValidationErrorDetail(
                        field="query",
                        message=f"Expected integer, got {value!r}",
                        value=value,
                    )
                ]
            ) from exc
    if target_type is float:
        try:
            return float(value)
        except (ValueError, TypeError) as exc:
            raise RequestValidationError(
                [
                    ValidationErrorDetail(
                        field="query",
                        message=f"Expected number, got {value!r}",
                        value=value,
                    )
                ]
            ) from exc
    return value
