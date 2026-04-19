"""Pre-computed parameter resolution plans — built once at route registration."""

from __future__ import annotations

import enum
import inspect
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin, get_type_hints

import msgspec

from hawkapi._compat.pydantic_adapter import is_pydantic_model
from hawkapi.background import BackgroundTasks
from hawkapi.di.depends import Depends
from hawkapi.validation.constraints import Body, Cookie, Header, ParamMarker, Path, Query


class ParamSource(enum.IntEnum):
    """Where a parameter value comes from. IntEnum for fast comparison."""

    PATH = 0
    QUERY = 1
    HEADER = 2
    COOKIE = 3
    BODY = 4
    DEPENDS_CALLABLE = 5
    DEPENDS_CONTAINER = 6
    CONTAINER_AUTO = 7
    REQUEST = 8
    BACKGROUND_TASKS = 9
    IMPLICIT_QUERY = 10
    IMPLICIT_PATH = 11


@dataclass(frozen=True, slots=True)
class DepCallablePlan:
    """Pre-computed plan for a Depends() callable's parameters."""

    callable: Any
    is_async: bool
    is_generator: bool
    is_async_generator: bool
    params: tuple[ParamSpec, ...]


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """Pre-computed instruction for resolving a single handler parameter."""

    name: str
    source: ParamSource
    base_type: Any = None
    alias: str | None = None
    # Marker defaults
    has_marker_default: bool = False
    marker_default: Any = field(default=..., repr=False)
    marker_default_factory: Any = field(default=None, repr=False)
    # Parameter defaults
    has_param_default: bool = False
    param_default: Any = field(default=..., repr=False)
    # Depends info
    dep_plan: DepCallablePlan | None = field(default=None, repr=False)
    dep_name: str | None = None
    # Body info
    is_pydantic: bool = False
    # Query/Header coercion
    coerce_type: type | None = None
    # Pre-computed header lookup key
    header_key: str | None = None


@dataclass(frozen=True, slots=True)
class HandlerPlan:
    """Complete pre-computed plan for a handler's parameter resolution."""

    params: tuple[ParamSpec, ...]
    is_async: bool
    has_background_tasks: bool
    bg_tasks_param_name: str | None
    needs_di_scope: bool
    needs_body: bool
    has_cleanup_deps: bool


# ---------------------------------------------------------------------------
# Helpers (same logic as resolver.py but run once at registration time)
# ---------------------------------------------------------------------------


def _get_annotation_marker(annotation: Any) -> ParamMarker | Depends | None:
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        for arg in args[1:]:
            if isinstance(arg, (ParamMarker, Depends)):
                return arg
    return None


def _get_base_type(annotation: Any) -> Any:
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


def _is_body_type(tp: Any) -> bool:
    try:
        if isinstance(tp, type) and issubclass(tp, (msgspec.Struct, dict, list)):
            return True
        return is_pydantic_model(tp)
    except TypeError:
        return False


def _unwrap_optional(tp: Any) -> Any:
    origin = get_origin(tp)
    if origin is not None:
        import types

        if origin in (types.UnionType,) or str(origin) == "typing.Union":
            args = get_args(tp)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return non_none[0]
    return tp


def _compute_coerce_type(base_type: Any) -> type | None:
    """Pre-compute the coercion target for query/header string values."""
    unwrapped = _unwrap_optional(base_type)
    if unwrapped in (int, float, bool):
        return unwrapped
    return None


# ---------------------------------------------------------------------------
# Plan builder for Depends() callables
# ---------------------------------------------------------------------------


def _build_dep_callable_plan(dep: Any) -> DepCallablePlan:
    """Build a resolution plan for a single Depends() callable."""
    target = dep.__call__ if callable(dep) and not inspect.isfunction(dep) else dep
    is_async = inspect.iscoroutinefunction(target)
    is_generator = inspect.isgeneratorfunction(target)
    is_async_generator = inspect.isasyncgenfunction(target)

    try:
        dep_hints = get_type_hints(target, include_extras=True)
    except Exception:
        dep_hints = getattr(target, "__annotations__", {})
    dep_sig = inspect.signature(target)

    params: list[ParamSpec] = []
    for dep_name, dep_param in dep_sig.parameters.items():
        if dep_name == "self":
            continue

        if dep_name == "request":
            params.append(ParamSpec(name=dep_name, source=ParamSource.REQUEST))
            continue

        dep_annotation = dep_hints.get(dep_name, dep_param.annotation)
        sub_marker = _get_annotation_marker(dep_annotation)

        # Check Annotated[..., Depends(...)]
        if isinstance(sub_marker, Depends) and sub_marker.dependency is not None:
            sub_plan = _build_dep_callable_plan(sub_marker.dependency)
            params.append(
                ParamSpec(
                    name=dep_name,
                    source=ParamSource.DEPENDS_CALLABLE,
                    dep_plan=sub_plan,
                )
            )
            continue

        # Check param.default = Depends(...)
        if isinstance(dep_param.default, Depends) and dep_param.default.dependency is not None:
            sub_plan = _build_dep_callable_plan(dep_param.default.dependency)
            params.append(
                ParamSpec(
                    name=dep_name,
                    source=ParamSource.DEPENDS_CALLABLE,
                    dep_plan=sub_plan,
                )
            )
            continue

        # Regular default
        if dep_param.default is not inspect.Parameter.empty:
            params.append(
                ParamSpec(
                    name=dep_name,
                    source=ParamSource.IMPLICIT_QUERY,
                    has_param_default=True,
                    param_default=dep_param.default,
                )
            )

    return DepCallablePlan(
        callable=dep,
        is_async=is_async,
        is_generator=is_generator,
        is_async_generator=is_async_generator,
        params=tuple(params),
    )


def build_side_effect_dep_plans(
    deps: Sequence[Depends] | None,
) -> tuple[DepCallablePlan, ...]:
    """Pre-compile a sequence of side-effect ``Depends(...)`` callables.

    Used for route-level and router-level ``dependencies=[Depends(...)]``
    lists where the return value is discarded. Each ``Depends.dependency`` is
    compiled via :func:`_build_dep_callable_plan` (sub-dependencies resolved
    recursively). ``Depends`` instances whose ``dependency`` is ``None`` — the
    named-only form — are skipped with a clear error, since side-effect deps
    must have a concrete callable.
    """
    if not deps:
        return ()
    plans: list[DepCallablePlan] = []
    for dep in deps:
        if dep.dependency is None:
            raise ValueError(
                f"side-effect dependencies must have a callable; got {dep!r} with dependency=None"
            )
        plans.append(_build_dep_callable_plan(dep.dependency))
    return tuple(plans)


# ---------------------------------------------------------------------------
# Main plan builder
# ---------------------------------------------------------------------------

_EMPTY_PARAMS: tuple[ParamSpec, ...] = ()


def build_handler_plan(
    handler: Any,
    *,
    container: Any | None = None,
    path_params: frozenset[str] | None = None,
) -> HandlerPlan:
    """Analyze handler signature and build a resolution plan.

    Called ONCE at route registration time. All inspect.signature() and
    get_type_hints() calls happen here, never on the request hot path.

    Args:
        handler: The route handler callable.
        container: Optional DI container for auto-resolve detection.
        path_params: Set of path parameter names extracted from route path.
    """
    is_async = inspect.iscoroutinefunction(handler)

    sig = inspect.signature(handler)
    try:
        hints = get_type_hints(handler, include_extras=True)
    except Exception:
        hints = getattr(handler, "__annotations__", {})

    params: list[ParamSpec] = []
    has_bg_tasks = False
    bg_tasks_name: str | None = None
    needs_scope = False
    needs_body = False
    has_cleanup = False
    _path_params = path_params or frozenset()

    for name, param in sig.parameters.items():
        annotation = hints.get(name, param.annotation)
        marker = _get_annotation_marker(annotation)
        base_type = _get_base_type(annotation)

        has_pdefault = param.default is not inspect.Parameter.empty
        pdefault = param.default if has_pdefault else ...

        if isinstance(marker, Path):
            params.append(
                ParamSpec(
                    name=name,
                    source=ParamSource.PATH,
                    base_type=base_type,
                    alias=marker.alias,
                    has_marker_default=marker.has_default(),
                    marker_default=marker.default,
                    marker_default_factory=marker.default_factory,
                )
            )

        elif isinstance(marker, Query):
            params.append(
                ParamSpec(
                    name=name,
                    source=ParamSource.QUERY,
                    base_type=base_type,
                    alias=marker.alias,
                    has_marker_default=marker.has_default(),
                    marker_default=marker.default,
                    marker_default_factory=marker.default_factory,
                    has_param_default=has_pdefault,
                    param_default=pdefault,
                    coerce_type=_compute_coerce_type(base_type),
                )
            )

        elif isinstance(marker, Header):
            params.append(
                ParamSpec(
                    name=name,
                    source=ParamSource.HEADER,
                    base_type=base_type,
                    alias=marker.alias,
                    has_marker_default=marker.has_default(),
                    marker_default=marker.default,
                    marker_default_factory=marker.default_factory,
                    has_param_default=has_pdefault,
                    param_default=pdefault,
                    header_key=(marker.alias or name).lower().replace("_", "-"),
                )
            )

        elif isinstance(marker, Cookie):
            params.append(
                ParamSpec(
                    name=name,
                    source=ParamSource.COOKIE,
                    base_type=base_type,
                    alias=marker.alias,
                    has_marker_default=marker.has_default(),
                    marker_default=marker.default,
                    marker_default_factory=marker.default_factory,
                    has_param_default=has_pdefault,
                    param_default=pdefault,
                )
            )

        elif isinstance(marker, Depends):
            if marker.dependency is not None:
                dep_plan = _build_dep_callable_plan(marker.dependency)
                if dep_plan.is_generator or dep_plan.is_async_generator:
                    has_cleanup = True
                params.append(
                    ParamSpec(
                        name=name,
                        source=ParamSource.DEPENDS_CALLABLE,
                        base_type=base_type,
                        dep_plan=dep_plan,
                    )
                )
            else:
                needs_scope = True
                params.append(
                    ParamSpec(
                        name=name,
                        source=ParamSource.DEPENDS_CONTAINER,
                        base_type=base_type,
                        dep_name=marker.name,
                        has_param_default=has_pdefault,
                        param_default=pdefault,
                    )
                )

        elif isinstance(marker, Body) or _is_body_type(base_type):
            needs_body = True
            params.append(
                ParamSpec(
                    name=name,
                    source=ParamSource.BODY,
                    base_type=base_type,
                    is_pydantic=(
                        is_pydantic_model(base_type) if isinstance(base_type, type) else False
                    ),
                    has_param_default=has_pdefault,
                    param_default=pdefault,
                )
            )

        elif name == "request":
            params.append(ParamSpec(name=name, source=ParamSource.REQUEST))

        elif isinstance(base_type, type) and issubclass(base_type, BackgroundTasks):
            has_bg_tasks = True
            bg_tasks_name = name
            params.append(ParamSpec(name=name, source=ParamSource.BACKGROUND_TASKS))

        elif name in _path_params:
            params.append(
                ParamSpec(
                    name=name,
                    source=ParamSource.IMPLICIT_PATH,
                    base_type=base_type,
                )
            )

        elif container is not None and isinstance(base_type, type) and container.has(base_type):
            needs_scope = True
            params.append(
                ParamSpec(
                    name=name,
                    source=ParamSource.CONTAINER_AUTO,
                    base_type=base_type,
                )
            )

        elif has_pdefault:
            params.append(
                ParamSpec(
                    name=name,
                    source=ParamSource.IMPLICIT_QUERY,
                    base_type=base_type,
                    has_param_default=True,
                    param_default=pdefault,
                    coerce_type=_compute_coerce_type(base_type),
                )
            )

        else:
            # Bare parameter — try query string at request time
            params.append(
                ParamSpec(
                    name=name,
                    source=ParamSource.IMPLICIT_QUERY,
                    base_type=base_type,
                    coerce_type=_compute_coerce_type(base_type),
                )
            )

    return HandlerPlan(
        params=tuple(params) if params else _EMPTY_PARAMS,
        is_async=is_async,
        has_background_tasks=has_bg_tasks,
        bg_tasks_param_name=bg_tasks_name,
        needs_di_scope=needs_scope,
        needs_body=needs_body,
        has_cleanup_deps=has_cleanup,
    )


def extract_path_param_names(path: str) -> frozenset[str]:
    """Extract parameter names from a route path like '/users/{user_id:int}'."""
    names: list[str] = []
    for segment in path.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            # Strip {name} or {name:type}
            inner = segment[1:-1]
            name = inner.split(":")[0]
            names.append(name)
    return frozenset(names)
