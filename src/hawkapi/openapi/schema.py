"""OpenAPI schema generation from registered routes."""

from __future__ import annotations

import inspect
from typing import Any, get_args, get_origin, get_type_hints

import msgspec

from hawkapi.di.depends import Depends
from hawkapi.openapi.inspector import type_to_schema
from hawkapi.routing.route import Route
from hawkapi.security.base import SecurityScheme
from hawkapi.validation.constraints import Body, Cookie, Header, ParamMarker, Path, Query


def generate_openapi(
    routes: list[Route],
    *,
    title: str = "HawkAPI",
    version: str = "0.1.0",
    description: str = "",
    api_version: str | None = None,
) -> dict[str, Any]:
    """Generate a complete OpenAPI 3.1 spec from registered routes."""
    paths: dict[str, dict[str, Any]] = {}
    schemas: dict[str, Any] = {}
    all_tags: set[str] = set()

    security_schemes: dict[str, Any] = {}

    filtered = routes
    if api_version is not None:
        filtered = [r for r in routes if r.version == api_version]

    for route in filtered:
        path_key = _convert_path(route.path)
        if path_key not in paths:
            paths[path_key] = {}

        operation, route_security = _build_operation(route, schemas)

        methods_to_add = [m.lower() for m in route.methods if m.lower() != "head"]
        for method_lower in methods_to_add:
            paths[path_key][method_lower] = operation if len(methods_to_add) <= 1 else {**operation}

        if route.tags:
            all_tags.update(route.tags)

        security_schemes.update(route_security)

    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": title,
            "version": version,
        },
        "paths": paths,
    }

    if description:
        spec["info"]["description"] = description

    if all_tags:
        spec["tags"] = [{"name": t} for t in sorted(all_tags)]

    components: dict[str, Any] = {}
    if schemas:
        components["schemas"] = schemas
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        spec["components"] = components

    return spec


def _convert_path(path: str) -> str:
    """Convert HawkAPI path format to OpenAPI format.

    /users/{user_id:int} -> /users/{user_id}
    """
    import re

    return re.sub(r"\{(\w+):\w+\}", r"{\1}", path)


def _build_operation(
    route: Route, schemas: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build an OpenAPI operation from a route.

    Returns (operation_dict, security_schemes_dict).
    """
    handler = route.handler
    try:
        hints = get_type_hints(handler, include_extras=True)
    except Exception:
        # Fallback for locally-defined types or forward reference failures
        hints = getattr(handler, "__annotations__", {})
    sig = inspect.signature(handler)

    operation: dict[str, Any] = {}

    if route.summary:
        operation["summary"] = route.summary
    if route.description:
        operation["description"] = route.description
    elif handler.__doc__:
        operation["description"] = handler.__doc__.strip()

    if route.name:
        operation["operationId"] = route.name

    if route.tags:
        operation["tags"] = route.tags

    if route.deprecated:
        operation["deprecated"] = True

    if route.permissions:
        operation["x-permissions"] = route.permissions

    parameters: list[dict[str, Any]] = []
    request_body_type: type | None = None
    body_example: Any = ...

    for name, param in sig.parameters.items():
        if name == "self" or name == "request":
            continue

        annotation = hints.get(name, param.annotation)
        if annotation is inspect.Parameter.empty:
            continue

        marker = _get_marker(annotation)
        base_type = _get_base_type(annotation)

        if isinstance(marker, Path) or name in _extract_path_params(route.path):
            example = marker.example if isinstance(marker, ParamMarker) else ...
            parameters.append(
                _build_parameter(
                    name=marker.alias if isinstance(marker, Path) and marker.alias else name,
                    location="path",
                    required=True,
                    annotation=base_type,
                    description=marker.description if isinstance(marker, ParamMarker) else None,
                    example=example,
                )
            )

        elif isinstance(marker, Query):
            parameters.append(
                _build_parameter(
                    name=marker.alias or name,
                    location="query",
                    required=(
                        param.default is inspect.Parameter.empty and not marker.has_default()
                    ),
                    annotation=base_type,
                    description=marker.description if marker else None,
                    example=marker.example,
                )
            )

        elif isinstance(marker, Header):
            parameters.append(
                _build_parameter(
                    name=(marker.alias or name).lower().replace("_", "-"),
                    location="header",
                    required=param.default is inspect.Parameter.empty and not marker.has_default(),
                    annotation=base_type,
                    description=marker.description,
                    example=marker.example,
                )
            )

        elif isinstance(marker, Cookie):
            parameters.append(
                _build_parameter(
                    name=marker.alias or name,
                    location="cookie",
                    required=param.default is inspect.Parameter.empty and not marker.has_default(),
                    annotation=base_type,
                    description=marker.description,
                    example=marker.example,
                )
            )

        elif isinstance(marker, Body) or _is_body_type(base_type):
            request_body_type = base_type
            if isinstance(marker, Body) and marker.example is not ...:
                body_example = marker.example

        elif (
            param.default is not inspect.Parameter.empty
            and isinstance(base_type, type)
            and issubclass(base_type, (str, int, float, bool))
        ):
            parameters.append(
                _build_parameter(
                    name=name,
                    location="query",
                    required=False,
                    annotation=base_type,
                )
            )

    if parameters:
        operation["parameters"] = parameters

    if request_body_type is not None:
        body_schema = type_to_schema(request_body_type)
        # Register in components if it's a struct
        if isinstance(request_body_type, type) and issubclass(request_body_type, msgspec.Struct):  # pyright: ignore[reportUnnecessaryIsInstance]
            schema_name = request_body_type.__name__
            schemas[schema_name] = body_schema
            body_schema = {"$ref": f"#/components/schemas/{schema_name}"}

        json_content: dict[str, Any] = {"schema": body_schema}
        if body_example is not ...:
            json_content["example"] = body_example
        operation["requestBody"] = {
            "required": True,
            "content": {"application/json": json_content},
        }

    # Detect security schemes from Depends(SecurityScheme) markers
    route_security: dict[str, Any] = {}
    security_requirements: list[dict[str, list[str]]] = []
    for name, param in sig.parameters.items():
        annotation = hints.get(name, param.annotation)
        depends = _get_depends_marker(annotation)
        if depends is not None and isinstance(depends.dependency, SecurityScheme):
            scheme_instance = depends.dependency
            scheme_name = type(scheme_instance).__name__
            route_security[scheme_name] = scheme_instance.openapi_scheme
            security_requirements.append({scheme_name: []})

    if security_requirements:
        operation["security"] = security_requirements

    # Build responses — prefer response_model over return type annotation
    responses: dict[str, Any] = {}
    response_type = route.response_model or hints.get("return")

    status = str(route.status_code)
    if response_type and response_type is not type(None):
        resp_schema = type_to_schema(response_type)
        if isinstance(response_type, type) and issubclass(response_type, msgspec.Struct):  # pyright: ignore[reportUnnecessaryIsInstance]
            schema_name = response_type.__name__
            schemas[schema_name] = resp_schema
            resp_schema = {"$ref": f"#/components/schemas/{schema_name}"}

        responses[status] = {
            "description": "Successful response",
            "content": {"application/json": {"schema": resp_schema}},
        }
    else:
        responses[status] = {"description": "Successful response"}

    operation["responses"] = responses

    return operation, route_security


def _build_parameter(
    name: str,
    location: str,
    required: bool,
    annotation: Any,
    description: str | None = None,
    example: Any = ...,
) -> dict[str, Any]:
    param: dict[str, Any] = {
        "name": name,
        "in": location,
        "required": required,
        "schema": (
            type_to_schema(annotation)
            if annotation is not inspect.Parameter.empty
            else {"type": "string"}
        ),
    }
    if description:
        param["description"] = description
    if example is not ...:
        param["example"] = example
    return param


def _get_marker(annotation: Any) -> ParamMarker | None:
    origin = get_origin(annotation)
    if origin is not None:
        for arg in get_args(annotation)[1:]:
            if isinstance(arg, ParamMarker):
                return arg
    return None


def _get_depends_marker(annotation: Any) -> Depends | None:
    """Extract a Depends marker from an Annotated type."""
    origin = get_origin(annotation)
    if origin is not None:
        for arg in get_args(annotation)[1:]:
            if isinstance(arg, Depends):
                return arg
    return None


def _get_base_type(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        if args:
            first = args[0]
            for arg in args[1:]:
                if isinstance(arg, (ParamMarker, msgspec.Meta)):
                    return first
    return annotation


def _is_body_type(tp: Any) -> bool:
    try:
        return isinstance(tp, type) and issubclass(tp, (msgspec.Struct, dict, list))  # pyright: ignore[reportUnnecessaryIsInstance]
    except TypeError:
        return False


def _extract_path_params(path: str) -> set[str]:
    import re

    return set(re.findall(r"\{(\w+)(?::\w+)?\}", path))
